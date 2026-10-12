"""SKAI episode metadata and unencrypted HLS downloads through the configured proxy."""
import json
import re
import subprocess
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlsplit

ALLOWED_HOSTS = {'www.skai.gr', 'skai.gr', 'videostream.skai.gr', 'ipapi.co'}
LIMIT = 2 * 1024 * 1024 * 1024


def validate_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('SKAI returned an unsupported video host or URL.')


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


opener = urllib.request.build_opener(SafeRedirect())


def fetch(url, limit=2 * 1024 * 1024):
    validate_url(url)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.skai.gr/tv/'})
    with opener.open(req, timeout=30) as response:
        result = response.read(limit + 1)
        if len(result) > limit:
            raise ValueError('The video response exceeds the supported size limit.')
        return result


def parse_episode(page):
    for match in re.finditer(r'var\s+data\s*=\s*', page):
        try:
            data, _ = json.JSONDecoder().raw_decode(page[match.end():])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get('episodemain'), dict):
            episode = data['episodemain']
            media = episode.get('media_item_file', '')
            if not isinstance(media, str) or not media.endswith('.mp4') or '..' in media or any(c in media for c in '?#\\'):
                raise ValueError('This SKAI episode uses an unsupported player.')
            if episode.get('drm'):
                raise ValueError('This episode is DRM-protected and cannot be downloaded.')
            return {
                'title': episode.get('media_item_title', 'SKAI episode'),
                'duration': None,
                'site': 'SKAI TV',
                'region': {'1': 'Greece', '2': 'Greece or Cyprus'}.get(str(episode.get('geolocation', '0')), ''),
                'stream': 'https://videostream.skai.gr/skaivod/_definst_/mp4:skai/' + media.lstrip('/') + '/chunklist.m3u8',
            }
    raise ValueError('No SKAI episode was found. Paste an individual episode page URL.')


def playlist_segments(text, playlist_url):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or lines[0] != '#EXTM3U' or '#EXT-X-ENDLIST' not in lines:
        raise ValueError('Only completed episode playlists are supported.')
    if any(line.startswith(('#EXT-X-KEY', '#EXT-X-MAP', '#EXT-X-BYTERANGE', '#EXT-X-STREAM-INF')) for line in lines):
        raise ValueError('This stream uses encryption or a playlist format that is not supported yet.')
    segments = [urljoin(playlist_url, line) for line in lines if not line.startswith('#')]
    if not segments:
        raise ValueError('The episode playlist is empty.')
    for url in segments:
        validate_url(url)
    return segments


def handle(mode, url, directory):
    parsed = urlsplit(url)
    if parsed.hostname not in {'www.skai.gr', 'skai.gr'} or not parsed.path.startswith('/tv/episode/'):
        raise ValueError('Paste a specific SKAI TV episode URL.')
    result = parse_episode(fetch(url).decode('utf-8'))
    stream = result.pop('stream')
    if mode == 'download':
        if result['region']:
            try:
                country = json.loads(fetch('https://ipapi.co/json/'))['country_code']
            except Exception as error:
                raise ValueError('Could not verify the server region. This episode is limited to ' + result['region'] + '.') from error
            allowed = {'GR', 'CY'} if result['region'] == 'Greece or Cyprus' else {'GR'}
            if country not in allowed:
                raise ValueError('SKAI limits this episode to ' + result['region'] + '. The download server is outside that region.')
        segments = playlist_segments(fetch(stream).decode('utf-8'), stream)
        source = Path(directory) / 'episode.ts'
        total = 0
        with source.open('wb') as output:
            for segment in segments:
                data = fetch(segment, limit=32 * 1024 * 1024)
                total += len(data)
                if total > LIMIT:
                    raise ValueError('This episode exceeds the 2 GB download limit.')
                output.write(data)
        filename = re.sub(r'[^\w .-]', '-', result['title'])[:100] + '.mp4'
        destination = Path(directory) / filename
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-protocol_whitelist', 'file',
                        '-i', str(source), '-c', 'copy', '-movflags', '+faststart', str(destination)],
                       check=True, capture_output=True, timeout=120)
        result['path'] = str(destination)
    return result


if __name__ == '__main__':
    import sys
    try:
        print(json.dumps(handle(*sys.argv[1:])))
    except ValueError as error:
        print(json.dumps({'error': str(error)}))
        sys.exit(1)
    except Exception:
        print(json.dumps({'error': 'SKAI could not provide this episode. It may be unavailable or access may be restricted.'}))
        sys.exit(1)

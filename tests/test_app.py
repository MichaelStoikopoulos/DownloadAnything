from pathlib import Path

import pytest
import app as application
from video_worker import public_address


@pytest.fixture
def client():
    return application.app.test_client()


def test_home(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b'Find video' in response.data


@pytest.mark.parametrize('body', [{}, {'url': 123}, {'url': 'file:///etc/passwd'}, {'url': 'https://user:pass@example.com'}])
def test_invalid_requests(client, body):
    assert client.post('/api/inspect', json=body).status_code == 400


@pytest.mark.parametrize('address', ['127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', '::ffff:127.0.0.1'])
def test_private_addresses_rejected(address):
    with pytest.raises(OSError):
        public_address(address)


def test_inspect_and_download(client, monkeypatch):
    def fake_worker(mode, url, directory):
        result = {'title': 'Sample video', 'duration': 12, 'site': 'Test'}
        if mode == 'download':
            path = Path(directory) / 'sample.mp4'
            path.write_bytes(b'test-video-content')
            result['path'] = str(path)
        return result
    monkeypatch.setattr(application, 'run_video', fake_worker)
    assert client.post('/api/inspect', json={'url': 'https://example.com/video'}).json['title'] == 'Sample video'
    response = client.post('/api/download', json={'url': 'https://example.com/video'})
    assert response.data == b'test-video-content'
    assert 'sample.mp4' in response.headers['Content-Disposition']
    response.close()


def test_localhost_blocked_by_real_worker(client):
    response = client.post('/api/inspect', json={'url': 'http://127.0.0.1:5000/'})
    assert response.status_code == 400


def test_skai_episode_metadata():
    from skai import parse_episode
    import json
    episode = {'media_item_file': 'shows/episode.mp4', 'media_item_title': 'An episode', 'geolocation': '2', 'drm': ''}
    page = 'var data = {"episode": []}; var data = ' + json.dumps({'episodemain': episode}) + ';'
    result = parse_episode(page)
    assert result['title'] == 'An episode'
    assert result['region'] == 'Greece or Cyprus'
    assert result['stream'].endswith('/mp4:skai/shows/episode.mp4/chunklist.m3u8')
    episode['drm'] = 'protected'
    with pytest.raises(ValueError, match='DRM'):
        parse_episode('var data = ' + json.dumps({'episodemain': episode}))


def test_skai_playlist():
    from skai import playlist_segments
    url = 'https://videostream.skai.gr/episode/chunklist.m3u8'
    assert playlist_segments('#EXTM3U\n#EXTINF:10,\nsegment.ts\n#EXT-X-ENDLIST', url) == ['https://videostream.skai.gr/episode/segment.ts']
    with pytest.raises(ValueError):
        playlist_segments('#EXTM3U\nhttp://127.0.0.1/secret\n#EXT-X-ENDLIST', url)
    with pytest.raises(ValueError, match='encryption'):
        playlist_segments('#EXTM3U\n#EXT-X-KEY:METHOD=AES-128\nsegment.ts\n#EXT-X-ENDLIST', url)


def test_skai_region_is_enforced(monkeypatch, tmp_path):
    import json
    import skai
    page = 'var data = ' + json.dumps({'episodemain': {'media_item_file': 'episode.mp4', 'geolocation': '2'}})
    def fetch(url, **kwargs):
        return b'{"country_code":"BE"}' if 'ipapi.co' in url else page.encode()
    monkeypatch.setattr(skai, 'fetch', fetch)
    with pytest.raises(ValueError, match='outside that region'):
        skai.handle('download', 'https://www.skai.gr/tv/episode/test', str(tmp_path))


def test_skai_download_remuxes_real_segments(monkeypatch, tmp_path):
    import json
    import subprocess
    import skai
    fixture = tmp_path / 'fixture.ts'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=64x64:d=1',
                    '-c:v', 'mpeg2video', '-f', 'mpegts', str(fixture)], check=True)
    segment = fixture.read_bytes()
    fixture.unlink()
    page = 'var data = ' + json.dumps({'episodemain': {'media_item_file': 'episode.mp4', 'media_item_title': 'Episode', 'geolocation': '0'}})
    def fetch(url, **kwargs):
        if '/tv/episode/' in url:
            return page.encode()
        if url.endswith('.m3u8'):
            return b'#EXTM3U\n#EXTINF:1,\nsegment.ts\n#EXT-X-ENDLIST'
        return segment
    monkeypatch.setattr(skai, 'fetch', fetch)
    result = skai.handle('download', 'https://www.skai.gr/tv/episode/test', str(tmp_path))
    path = Path(result['path'])
    assert path.suffix == '.mp4'
    assert b'ftyp' in path.read_bytes()[:32]
    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type', '-of', 'json', str(path)], capture_output=True, text=True, check=True)
    assert json.loads(probe.stdout)['streams'][0]['codec_type'] == 'video'


def test_native_download_reports_error_to_page(client):
    response = client.post('/download', data={'url': 'file:///etc/passwd'})
    assert response.status_code == 400
    assert b'parent.postMessage' in response.data

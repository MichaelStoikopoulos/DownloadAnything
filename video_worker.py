"""Isolated extraction worker; refuse connections to non-public addresses."""
import ipaddress
import json
import socket
import sys
from pathlib import Path

original_getaddrinfo = socket.getaddrinfo
original_socket = socket.socket


def public_address(address):
    ip = ipaddress.ip_address(address.split('%')[0])
    if not ip.is_global or (ip.version == 6 and ip.ipv4_mapped and not ip.ipv4_mapped.is_global):
        raise OSError('Only public internet addresses are allowed')


def public_getaddrinfo(*args, **kwargs):
    results = original_getaddrinfo(*args, **kwargs)
    for result in results:
        public_address(result[4][0])
    return results


class PublicSocket(original_socket):
    def connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            public_address(address[0])
        return super().connect(address)

    def connect_ex(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            public_address(address[0])
        return super().connect_ex(address)


socket.getaddrinfo = public_getaddrinfo
socket.socket = PublicSocket

import yt_dlp


class QuietLogger:
    def debug(self, message):
        pass
    def warning(self, message):
        pass
    def error(self, message):
        print(message, file=sys.stderr)


def main():
    mode, url, directory = sys.argv[1:]
    options = {
        'quiet': True, 'no_warnings': True, 'logger': QuietLogger(),
        'noplaylist': True, 'playlistend': 1, 'socket_timeout': 20,
        'retries': 1, 'fragment_retries': 1, 'proxy': '',
        'outtmpl': str(Path(directory) / '%(title).100B-%(id)s.%(ext)s'),
        # One existing audio/video file keeps downloading inside the guarded worker.
        'format': 'best[ext=mp4]/best', 'max_filesize': 500 * 1024 * 1024,
    }
    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(url, download=False)
        if info.get('_type') in ('playlist', 'multi_video'):
            info = next((entry for entry in info.get('entries', []) if entry), None)
        if not info:
            raise ValueError('No video found')
        if info.get('is_live'):
            raise ValueError('Live streams are not supported')
        result = {'title': info.get('title', 'Video'), 'duration': info.get('duration'),
                  'site': info.get('extractor_key', 'Website')}
        if mode == 'download':
            downloader.process_info(info)
            files = [p for p in Path(directory).iterdir() if p.is_file() and p.suffix not in ('.part', '.ytdl')]
            if len(files) != 1 or files[0].stat().st_size > 500 * 1024 * 1024:
                raise ValueError('Video exceeds the 500 MB limit or could not be downloaded')
            result['path'] = str(files[0])
        print(json.dumps(result))


if __name__ == '__main__':
    main()

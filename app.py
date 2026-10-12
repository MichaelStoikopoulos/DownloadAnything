import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request, send_file, Response

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 8192


def run_video(mode, url, directory):
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Enter a valid public http or https URL without credentials.')
    skai = parsed.hostname in ('www.skai.gr', 'skai.gr')
    worker = 'skai.py' if skai else 'video_worker.py'
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name(worker)), mode, url, directory],
            capture_output=True, text=True, timeout=(1200 if skai else 300) if mode == 'download' else 60,
        )
    except subprocess.TimeoutExpired:
        raise ValueError('The site took too long to respond. Try again or use another URL.')
    if result.returncode:
        if skai:
            try:
                error = json.loads(result.stdout).get('error')
            except (json.JSONDecodeError, AttributeError):
                error = None
            if error:
                raise ValueError(error)
        raise ValueError('This video could not be accessed. The site may be unsupported, private, or protected.')
    return json.loads(result.stdout)


@app.get('/')
def index():
    return render_template('index.html')


@app.post('/api/inspect')
def inspect():
    with tempfile.TemporaryDirectory(prefix='downloadanything-') as directory:
        return jsonify(run_video('inspect', get_url(), directory))


def get_url():
    body = dict(request.form) if request.path == '/download' else request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get('url'), str):
        raise ValueError('Paste a video page URL first.')
    return body['url'].strip()


@app.post('/download')
@app.post('/api/download')
def download():
    directory = tempfile.mkdtemp(prefix='downloadanything-')
    try:
        result = run_video('download', get_url(), directory)
        path = Path(result['path']).resolve()
        if not path.is_relative_to(Path(directory).resolve()) or not path.is_file():
            raise ValueError('No downloadable video was found.')
        # Keep the open descriptor alive for streaming, then remove temporary files.
        stream = path.open('rb')
        try:
            response = send_file(stream, as_attachment=True, download_name=path.name,
                                 mimetype='application/octet-stream')
            response.content_length = path.stat().st_size
            response.call_on_close(stream.close)
            return response
        except Exception:
            stream.close()
            raise
    finally:
        shutil.rmtree(directory, ignore_errors=True)


@app.errorhandler(ValueError)
def bad_request(error):
    if request.path == '/download':
        payload = json.dumps({'type': 'download-error', 'error': str(error)}).replace('<', chr(92) + 'u003c')
        return Response('<script>parent.postMessage(' + payload + ', location.origin)</script>', status=400, mimetype='text/html')
    return jsonify(error=str(error)), 400


@app.errorhandler(413)
def too_large(error):
    return jsonify(error='The URL is too long.'), 413


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

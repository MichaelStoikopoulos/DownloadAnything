# DownloadAnything

Paste a video page URL, inspect its title and duration, then download an available combined video/audio file. Flask serves the responsive UI and yt-dlp handles supported websites.

## Run

Requires Python 3.12 or newer. FFmpeg is available in the cloud environment but is not required for the default combined-file format.

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

The server listens on port 5000. To test:

```sh
.venv/bin/pip install pytest
.venv/bin/python -m pytest -q
```

SKAI TV episode pages use a dedicated parser for the site’s embedded `episodemain` data and official unencrypted HLS stream. The parser checks the download server’s country through ipapi.co when SKAI marks an episode as region-limited, and returns a clear error outside the permitted region. FFmpeg is required for SKAI downloads to remux the stream into MP4. SKAI network requests use the environment proxy and permit only explicitly listed HTTPS hosts, with redirect validation.

Downloads use temporary files that are removed after opening the response stream. Each extraction runs in an isolated subprocess with a timeout. For non-SKAI URLs, public-address checks apply to DNS results and outbound socket connections, including redirects; that generic worker requires direct network access and does not use environment proxies. No login cookies or credentials are accepted.

Only download videos you own or have permission to save. DRM-protected content and login-only sites are unsupported. Downloads prefer an existing MP4 with both audio and video, falling back to another combined format; highest-quality separate streams are not merged. Generic downloads have a 500 MB limit (unknown-size transfers are checked after completion) and five-minute timeout. SKAI episodes have a 2 GB limit and twenty-minute timeout; encrypted, live, fragmented-MP4, and master playlists are unsupported. Site compatibility depends on yt-dlp and can change.

This is a development server. Before public deployment, use a production WSGI server, authentication/rate limits, bounded worker concurrency, and infrastructure egress and storage limits. Downloads use a native browser form submission so large files stream without being buffered in JavaScript.

## Verified SKAI example

The episode page `https://www.skai.gr/tv/episode/psuchagogia/the-voice-of-greece-powered-by-telekom/2026-10-11-21` was successfully inspected as “The Voice of Greece powered by Telekom | 11/10/2026”. It is marked available in Greece or Cyprus. A real full-episode download has not been verified.

const form = document.querySelector('#form');
const input = document.querySelector('#url');
const find = document.querySelector('#find');
const download = document.querySelector('#download');
const status = document.querySelector('#status');
const result = document.querySelector('#result');
let selectedUrl = '';
function message(text, error = false) { status.textContent = text; status.classList.toggle('error', error); }
input.addEventListener('input', () => { result.hidden = true; selectedUrl = ''; });
form.addEventListener('submit', async event => {
  event.preventDefault();
  find.disabled = true;
  result.hidden = true;
  const url = input.value.trim();
  message('Looking for your video…');
  try {
    const response = await fetch('/api/inspect', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Could not find a video.');
    if (input.value.trim() !== url) { message('The link changed. Find the video again.'); return; }
    selectedUrl = url;
    document.querySelector('#title').textContent = data.title;
    const duration = data.duration ? `${Math.floor(data.duration / 60)}:${String(Math.floor(data.duration % 60)).padStart(2, '0')}` : 'Duration unavailable';
    document.querySelector('#meta').textContent = `${data.site} · ${duration}${data.region ? ' · Available in ' + data.region : ''}`;
    result.hidden = false;
    message('Video found. Ready when you are.');
  } catch (error) { message(error.message, true); }
  finally { find.disabled = false; }
});
window.addEventListener('message', event => {
  if (event.origin === location.origin && event.data?.type === 'download-error') {
    message(event.data.error, true);
    download.disabled = false;
  }
});
download.addEventListener('click', () => {
  if (!selectedUrl) return;
  const frame = document.createElement('iframe');
  frame.hidden = true;
  frame.name = `download-${Date.now()}`;
  document.body.appendChild(frame);
  const downloadForm = document.createElement('form');
  downloadForm.method = 'POST';
  downloadForm.action = '/download';
  downloadForm.target = frame.name;
  const field = document.createElement('input');
  field.type = 'hidden';
  field.name = 'url';
  field.value = selectedUrl;
  downloadForm.appendChild(field);
  document.body.appendChild(downloadForm);
  downloadForm.submit();
  downloadForm.remove();
  message('Preparing your video… Your browser will save it when ready. Full episodes may take several minutes.');
  download.disabled = true;
  setTimeout(() => { download.disabled = false; }, 5000);
});

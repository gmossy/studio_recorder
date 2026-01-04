"""FastAPI web audio recorder (browser-based mic capture).

This replaces the Tkinter UI so it works cleanly with the Python 3.12.11
virtual environment even when Tcl/Tk is not available.

Features:
- In-browser microphone recording (MediaRecorder)
- Live audio level meter and oscilloscope trace (WebAudio Analyser)
- Noise gate / auto-pause on silence (configurable threshold + hold)
- Microphone device selector (choose any audio input)
- Trim/crop before saving (start/end seconds passed to ffmpeg)
- Playback with scrub timeline slider
- Keyboard shortcuts: Space (start/stop), Ctrl+S (save)
- About modal (creator/date)
- User-selected save location (File System Access API) with fallback
- Upload to FastAPI backend
- Converts to MP3 using local ./ffmpeg (preferred) or system ffmpeg
- Playback and download of last recordings

Author: Glenn Mossy
Date: Jan 4, 2025
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # Optional: graceful if not installed
else:
    load_dotenv()

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import sys

APP_TITLE = "Studio Recorder"
BASE_DIR = Path(__file__).resolve().parent
RECORDINGS_DIR = BASE_DIR / "recordings"
RECORDINGS_DIR.mkdir(exist_ok=True)


def _ffmpeg_bin() -> str:
    local = BASE_DIR / "ffmpeg"
    if local.exists() and os.access(local, os.X_OK):
        return str(local)
    return "ffmpeg"


def _safe_stem(name: str) -> str:
    stem = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
    return stem.strip("_") or "recording"


def _timestamp_name(prefix: str = "recording") -> str:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{prefix}_{ts}"


app = FastAPI(title=APP_TITLE)
app.mount("/recordings", StaticFiles(directory=str(RECORDINGS_DIR)), name="recordings")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{APP_TITLE}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    :root {{
      --bg: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
      --card: rgba(30,41,59,0.65);
      --card-border: rgba(148,163,184,0.12);
      --text: #e2e8f0;
      --muted: #94a3b8;
      --accent: linear-gradient(135deg, #f97316 0%, #fb923c 100%);
      --good: #22c55e;
      --bad: #ef4444;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin:0;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
    }}
    .wrap {{
      max-width: 860px;
      margin: 0 auto;
      padding: 32px 20px;
    }}
    .title {{
      font-size: 36px;
      font-weight: 700;
      letter-spacing: -0.02em;
      background: linear-gradient(135deg, #f97316, #fb923c);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }}
    .subtitle {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 16px;
      font-weight: 500;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1.3fr 0.9fr;
      gap: 20px;
      margin-top: 24px;
    }}
    .card {{
      background: var(--card);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border-radius: 20px;
      padding: 24px;
      box-shadow: 0 20px 40px rgba(0,0,0,0.25), 0 0 0 1px var(--card-border);
      border: 1px solid var(--card-border);
      transition: transform 0.3s ease, box-shadow 0.3s ease;
    }}
    .card:hover {{
      transform: translateY(-2px);
      box-shadow: 0 24px 48px rgba(0,0,0,0.3), 0 0 0 1px var(--card-border);
    }}
    .row {{ display:flex; align-items:center; gap:12px; flex-wrap: wrap; }}
    button {{
      border:0;
      padding: 14px 18px;
      border-radius: 14px;
      font-weight: 600;
      cursor: pointer;
      font-family: inherit;
      font-size: 15px;
      transition: all 0.2s ease;
      position: relative;
      overflow: hidden;
    }}
    button::before {{
      content: '';
      position: absolute;
      top: 0; left: 0; width: 100%; height: 100%;
      background: linear-gradient(135deg, rgba(255,255,255,0.1), transparent);
      opacity: 0;
      transition: opacity 0.3s ease;
    }}
    button:hover::before {{ opacity: 1; }}
    .primary {{
      background: var(--accent);
      color: #0f172a;
      box-shadow: 0 4px 14px rgba(249,115,22,0.3);
    }}
    .primary:hover {{
      transform: translateY(-1px);
      box-shadow: 0 6px 20px rgba(249,115,22,0.4);
    }}
    .danger {{
      background: var(--bad);
      color: #0f172a;
      box-shadow: 0 4px 14px rgba(239,68,68,0.3);
    }}
    .danger:hover {{
      transform: translateY(-1px);
      box-shadow: 0 6px 20px rgba(239,68,68,0.4);
    }}
    .ghost {{
      background: rgba(148,163,184,0.08);
      color: var(--text);
      border: 1px solid rgba(148,163,184,0.2);
      backdrop-filter: blur(8px);
    }}
    .ghost:hover {{
      background: rgba(148,163,184,0.14);
      border-color: rgba(148,163,184,0.3);
    }}
    button:disabled {{ opacity: .4; cursor: not-allowed; transform: none !important; }}
    .pill {{
      padding: 8px 14px;
      border-radius: 999px;
      background: rgba(148,163,184,0.12);
      color: var(--muted);
      font-size: 13px;
      font-weight: 600;
      backdrop-filter: blur(8px);
    }}
    canvas {{
      width: 100%;
      height: 140px;
      background: rgba(11,18,35,0.6);
      border-radius: 16px;
      box-shadow: inset 0 2px 8px rgba(0,0,0,0.3);
    }}
    .meter {{
      height: 10px;
      width: 100%;
      background: rgba(148,163,184,0.12);
      border-radius: 999px;
      overflow:hidden;
      box-shadow: inset 0 1px 3px rgba(0,0,0,0.3);
    }}
    .meter > div {{
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, var(--good), #10b981);
      transition: width 60ms linear;
      box-shadow: 0 0 8px rgba(34,197,94,0.4);
    }}
    .small {{ font-size: 13px; color: var(--muted); font-weight: 500; }}
    a {{ color: var(--text); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    input[type=text], input[type=number], select {{
      background: rgba(11,18,35,0.5);
      border: 1px solid rgba(148,163,184,0.2);
      color: var(--text);
      padding: 12px 14px;
      border-radius: 12px;
      width: 100%;
      font-family: inherit;
      font-size: 15px;
      backdrop-filter: blur(8px);
      transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }}
    input[type=text]:focus, input[type=number]:focus, select:focus {{
      outline: none;
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(249,115,22,0.15);
    }}
    input[type=range] {{
      width: 100%;
      height: 6px;
      background: rgba(148,163,184,0.12);
      border-radius: 3px;
      outline: none;
      -webkit-appearance: none;
    }}
    input[type=range]::-webkit-slider-thumb {{
      -webkit-appearance: none;
      width: 18px;
      height: 18px;
      background: var(--accent);
      border-radius: 50%;
      cursor: pointer;
      box-shadow: 0 2px 6px rgba(0,0,0,0.3);
    }}
    .modal-backdrop {{
      position: fixed;
      inset: 0;
      background: rgba(2,6,23,0.75);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      display:none;
      align-items: center;
      justify-content: center;
      padding: 20px;
      animation: fadeIn 0.2s ease;
    }}
    .modal {{
      width: min(540px, 96vw);
      background: var(--card);
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      border-radius: 20px;
      padding: 24px;
      box-shadow: 0 24px 48px rgba(0,0,0,0.35), 0 0 0 1px var(--card-border);
      border: 1px solid var(--card-border);
      animation: slideUp 0.3s ease;
    }}
    .modal h3 {{ margin: 0; font-size: 20px; font-weight: 700; }}
    .modal .meta {{ margin-top: 16px; color: var(--muted); font-size: 14px; line-height: 1.5; }}
    .modal .actions {{ display:flex; justify-content: flex-end; margin-top: 20px; }}
    .about-btn, .settings-btn {{ padding: 10px 12px; border-radius: 999px; font-size: 13px; }}
    kbd {{
      background: rgba(148,163,184,0.12);
      border: 1px solid rgba(148,163,184,0.2);
      border-radius: 6px;
      padding: 2px 6px;
      font-size: 12px;
      font-family: monospace;
      color: var(--text);
    }}
    @keyframes fadeIn {{
      from {{ opacity: 0; }}
      to {{ opacity: 1; }}
    }}
    @keyframes slideUp {{
      from {{ opacity: 0; transform: translateY(12px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes pulse {{
      0%, 100% {{ opacity: 1; }}
      50% {{ opacity: 0.4; }}
    }}
    .pulse {{ animation: pulse 1.5s ease-in-out infinite; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"title\">Studio Recorder</div>
    <div class=\"subtitle\">Record in your browser, upload to Python, save MP3, and play back instantly.</div>

    <div class=\"grid\">
      <div class=\"card\">
        <div class=\"row\" style=\"justify-content:space-between\">
          <div class=\"row\">
            <div class=\"pill\" id=\"status\">Idle</div>
            <div class=\"pill\" id=\"timer\">00:00</div>
            <span id=\"mainAutoGcsIndicator\" style=\"display:none; margin-left:8px; font-size:13px; color: var(--accent);\" title=\"Auto-uploading to GCS\">☁️</span>
            <span id=\"mainAutoTranscribeIndicator\" style=\"display:none; margin-left:4px; font-size:13px; color: var(--accent);\" title=\"Auto-transcribing\">📝</span>
          </div>
          <div style=\"display:flex; gap:8px\">
            <button class=\"ghost settings-btn\" id=\"settingsBtn\" type=\"button\" title=\"Settings\">⚙️</button>
            <button class=\"ghost about-btn\" id=\"aboutBtn\" type=\"button\">About</button>
          </div>
        </div>

        <div style=\"margin-top: 14px\">
          <canvas id=\"scope\" width=\"760\" height=\"140\"></canvas>
          <div style=\"margin-top:10px\" class=\"meter\"><div id=\"level\"></div></div>
          <div class=\"small\" style=\"margin-top:8px\">If you don’t see movement, allow microphone access in the browser prompt.</div>
        </div>

        <div class=\"row\" style=\"margin-top: 14px\">
          <button class=\"primary\" id=\"startBtn\">● Start</button>
          <button class=\"danger\" id=\"stopBtn\" disabled>■ Stop</button>
          <button class=\"ghost\" id=\"saveBtn\" disabled>💾 Save</button>
          <button class=\"ghost\" id=\"playBtn\" disabled>▶︎ Play Last MP3</button>
        </div>
      </div>

      <div class=\"card\">
        <div style=\"font-weight:800\">Save Settings</div>
        <div class=\"small\" style=\"margin-top:12px\">Trim before saving (seconds)</div>
        <div class=\"row\" style=\"margin-top:8px\">
          <div style=\"flex:1\"><input id=\"trimStart\" type=\"number\" step=\"0.1\" min=\"0\" placeholder=\"Start\" /></div>
          <div style=\"flex:1\"><input id=\"trimEnd\" type=\"number\" step=\"0.1\" min=\"0\" placeholder=\"End\" /></div>
        </div>

        <div class=\"small\" style=\"margin-top:12px\">Auto-pause on silence</div>
        <div class=\"row\" style=\"margin-top:8px\">
          <label class=\"small\" style=\"display:flex; align-items:center; gap:8px\">
            <input id=\"gateEnabled\" type=\"checkbox\" checked /> Enabled
          </label>
          <div style=\"flex:1\">
            <div class=\"small\">Threshold</div>
            <input id=\"gateThreshold\" type=\"range\" min=\"1\" max=\"25\" value=\"7\" />
          </div>
          <div style=\"width:120px\">
            <div class=\"small\">Hold (ms)</div>
            <input id=\"gateHold\" type=\"number\" min=\"100\" step=\"100\" value=\"800\" />
          </div>
        </div>

        <div style=\"margin-top: 14px\" class=\"small\">Last saved</div>
        <div id=\"lastSaved\" style=\"margin-top:6px\">None</div>

        <div style=\"margin-top: 12px\" class=\"small\">Last duration</div>
        <div id=\"lastDuration\" style=\"margin-top:6px\">None</div>

        <div style=\"margin-top: 12px\" class=\"small\">Download</div>
        <div id=\"downloadStatus\" style=\"margin-top:6px\">Not downloaded</div>
        <div style=\"margin-top: 12px\" class=\"small\">Auto</div>
        <div id=\"autoStatus\" style=\"margin-top:6px\">Disabled</div>
        <div id=\"links\" style=\"margin-top:10px\"></div>
        <audio id=\"player\" controls style=\"width:100%; margin-top: 12px; display:none\"></audio>
        <div id=\"scrubWrap\" style=\"margin-top:10px; display:none\">
          <input id=\"scrub\" type=\"range\" min=\"0\" max=\"0\" step=\"0.01\" value=\"0\" />
          <div class=\"small\" id=\"scrubLabel\" style=\"margin-top:6px\">00:00 / 00:00</div>
        </div>

        <div style=\"margin-top: 14px\" class=\"small\">Backend</div>
        <div class=\"small\">Uploads: <code>/api/upload</code></div>
        <div class=\"small\">Saved files: <code>/recordings/&lt;file&gt;</code></div>
      </div>
    </div>
  </div>

  <div class=\"modal-backdrop\" id=\"settingsBackdrop\" role=\"dialog\" aria-modal=\"true\" aria-labelledby=\"settingsTitle\">
    <div class=\"modal\">
      <h3 id=\"settingsTitle\">Settings</h3>
      <div class=\"meta\">
        <div style=\"margin-bottom:14px\">
          <div class=\"small\" style=\"margin-bottom:4px\">Input device</div>
          <select id=\"deviceSelect\"><option value=\"\">Default microphone</option></select>
        </div>
        <div style=\"margin-bottom:14px\">
          <div class=\"small\" style=\"margin-bottom:4px\">Filename base (timestamp will be appended)</div>
          <input id=\"nameBase\" type=\"text\" value=\"recording\" />
        </div>
        <div style=\"margin-bottom:14px\">
          <label class=\"small\" style=\"display:flex; align-items:center; gap:8px\">
            <input id=\"autoUploadGcs\" type=\"checkbox\" /> Auto-upload to GCS
            <span id=\"autoGcsIndicator\" style=\"display:none; margin-left:4px; font-size:10px; color: var(--accent);\">⏳</span>
          </label>
        </div>
        <div style=\"margin-bottom:14px\">
          <label class=\"small\" style=\"display:flex; align-items:center; gap:8px\">
            <input id=\"autoTranscribe\" type=\"checkbox\" /> Auto-transcribe with gc_stt.py
            <span id=\"autoTranscribeIndicator\" style=\"display:none; margin-left:4px; font-size:10px; color: var(--accent);\">⏳</span>
          </label>
        </div>
      </div>
      <div class=\"actions\">
        <button class=\"primary\" id=\"settingsCloseBtn\" type=\"button\">Close</button>
      </div>
    </div>
  </div>

  <div class=\"modal-backdrop\" id=\"aboutBackdrop\" role=\"dialog\" aria-modal=\"true\" aria-labelledby=\"aboutTitle\">
    <div class=\"modal\">
      <h3 id=\"aboutTitle\">About Studio Recorder</h3>
      <div class=\"meta\">
        <div><strong>Creator:</strong> Glenn Mossy</div>
        <div><strong>Date:</strong> Jan 4, 2025</div>
        <div style=\"margin-top:12px\"><strong>Features</strong></div>
        <ul style=\"margin:6px 0 0 16px; padding:0;\">
          <li>Browser microphone recording with live oscilloscope</li>
          <li>Noise gate / auto-pause on silence</li>
          <li>Microphone device selector</li>
          <li>Trim/crop before saving</li>
          <li>Playback with scrub timeline</li>
          <li>Auto-upload to Google Cloud Storage</li>
          <li>Auto-transcribe with gc_stt.py</li>
          <li>User-selected save location</li>
        </ul>
        <div style=\"margin-top:12px\"><strong>Keyboard shortcuts</strong></div>
        <ul style=\"margin:6px 0 0 16px; padding:0;\">
          <li><kbd>Space</kbd> — Start / Stop recording</li>
          <li><kbd>Ctrl+S</kbd> — Save recording</li>
          <li><kbd>Esc</kbd> — Close modals</li>
        </ul>
        <div style=\"margin-top:12px\">FastAPI backend + browser microphone recorder.</div>
      </div>
      <div class=\"actions\">
        <button class=\"primary\" id=\"aboutCloseBtn\" type=\"button\">Close</button>
      </div>
    </div>
  </div>

<script>
  const startBtn = document.getElementById('startBtn');
  const stopBtn = document.getElementById('stopBtn');
  const saveBtn = document.getElementById('saveBtn');
  const playBtn = document.getElementById('playBtn');
  const statusPill = document.getElementById('status');
  const timerPill = document.getElementById('timer');
  const canvas = document.getElementById('scope');
  const ctx = canvas.getContext('2d');
  const levelBar = document.getElementById('level');
  const nameBase = document.getElementById('nameBase');
  const lastSaved = document.getElementById('lastSaved');
  const lastDuration = document.getElementById('lastDuration');
  const downloadStatus = document.getElementById('downloadStatus');
  const autoStatus = document.getElementById('autoStatus');
  const deviceSelect = document.getElementById('deviceSelect');
  const gateEnabled = document.getElementById('gateEnabled');
  const gateThreshold = document.getElementById('gateThreshold');
  const gateHold = document.getElementById('gateHold');
  const trimStart = document.getElementById('trimStart');
  const trimEnd = document.getElementById('trimEnd');
  const links = document.getElementById('links');
  const player = document.getElementById('player');
  const scrubWrap = document.getElementById('scrubWrap');
  const scrub = document.getElementById('scrub');
  const scrubLabel = document.getElementById('scrubLabel');
  const aboutBtn = document.getElementById('aboutBtn');
  const aboutBackdrop = document.getElementById('aboutBackdrop');
  const aboutCloseBtn = document.getElementById('aboutCloseBtn');
  const settingsBtn = document.getElementById('settingsBtn');
  const settingsBackdrop = document.getElementById('settingsBackdrop');
  const settingsCloseBtn = document.getElementById('settingsCloseBtn');
  const autoUploadGcs = document.getElementById('autoUploadGcs');
  const autoTranscribe = document.getElementById('autoTranscribe');
  const autoGcsIndicator = document.getElementById('autoGcsIndicator');
  const autoTranscribeIndicator = document.getElementById('autoTranscribeIndicator');
  const mainAutoGcsIndicator = document.getElementById('mainAutoGcsIndicator');
  const mainAutoTranscribeIndicator = document.getElementById('mainAutoTranscribeIndicator');

  let mediaRecorder;
  let chunks = [];
  let audioCtx;
  let analyser;
  let source;
  let dataArray;
  let rafId;
  let startTs;
  let timerId;
  let lastMp3Url;
  let lastBlob;
  let lastRecordedMs;
  let stream;
  let recordingActive = false;
  let gatePaused = false;
  let silenceStartedAt = null;

  function openAbout() {{
    aboutBackdrop.style.display = 'flex';
  }}

  function closeAbout() {{
    aboutBackdrop.style.display = 'none';
  }}

  function openSettings() {{
    settingsBackdrop.style.display = 'flex';
  }}

  function closeSettings() {{
    settingsBackdrop.style.display = 'none';
  }}

  function setStatus(text) {{ statusPill.textContent = text; }}

  function fmtTime(ms) {{
    const sec = Math.floor(ms/1000);
    const m = String(Math.floor(sec/60)).padStart(2,'0');
    const s = String(sec%60).padStart(2,'0');
    const secsOnly = sec % 60;
    return `${{m}}:${{String(secsOnly).padStart(2,'0')}} (${{(ms/1000).toFixed(1)}}s)`;
  }}

  async function refreshDevices() {{
    try {{
      const devices = await navigator.mediaDevices.enumerateDevices();
      const mics = devices.filter(d => d.kind === 'audioinput');
      const current = deviceSelect.value;
      deviceSelect.innerHTML = '<option value="">Default microphone</option>';
      for (const d of mics) {{
        const opt = document.createElement('option');
        opt.value = d.deviceId;
        opt.textContent = d.label || `Microphone (${{d.deviceId.slice(0,6)}}…)`;
        deviceSelect.appendChild(opt);
      }}
      deviceSelect.value = current;
    }} catch (e) {{
      console.warn('enumerateDevices failed', e);
    }}
  }}

  function triggerDownload(url, filename) {{
    // Browsers will save to the user’s default Downloads folder (or whatever they configured).
    const a = document.createElement('a');
    a.href = new URL(url, window.location.href).toString();
    a.download = filename || '';
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    a.remove();
  }}

  async function saveWithPicker(url, filename) {{
    // If supported, prompt the user for a save location.
    // Falls back to normal browser download if the API isn't available.
    if (window.showSaveFilePicker) {{
      try {{
        const handle = await window.showSaveFilePicker({{
          suggestedName: filename || 'recording.mp3',
          types: [{{
            description: 'MP3 Audio',
            accept: {{ 'audio/mpeg': ['.mp3'] }}
          }}]
        }});

        const resp = await fetch(new URL(url, window.location.href).toString());
        if (!resp.ok) throw new Error('Download failed: ' + resp.status);
        const blob = await resp.blob();
        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
        downloadStatus.textContent = 'Saved: ' + (filename || 'recording.mp3');
        return; // Do not trigger fallback download
      }} catch (err) {{
        if (err && err.name === 'AbortError') {{
          downloadStatus.textContent = 'Save canceled';
          return;
        }}
        console.error(err);
        downloadStatus.textContent = 'Save failed';
        // Continue to fallback download.
      }}
    }}

    // Fallback: normal browser download
    triggerDownload(url, filename);
    downloadStatus.textContent = 'Downloaded: ' + (filename || 'recording.mp3');
  }}

  function draw() {{
    if (!analyser) return;
    analyser.getByteTimeDomainData(dataArray);
    ctx.fillStyle = '#0b1223';
    ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.lineWidth = 2;
    ctx.strokeStyle = '#f97316';
    ctx.beginPath();
    const sliceWidth = canvas.width / dataArray.length;
    let x = 0;
    let sum = 0;
    for (let i=0;i<dataArray.length;i++) {{
      const v = dataArray[i] / 128.0;
      const y = (v * canvas.height) / 2;
      const dv = (dataArray[i] - 128) / 128;
      sum += dv*dv;
      if (i===0) ctx.moveTo(x,y);
      else ctx.lineTo(x,y);
      x += sliceWidth;
    }}
    ctx.stroke();
    const rms = Math.sqrt(sum / dataArray.length);
    const pct = Math.min(1, rms*1.8);
    levelBar.style.width = `${{Math.floor(pct*100)}}%`;

    // Noise gate / auto-pause on silence.
    if (recordingActive && mediaRecorder && mediaRecorder.state) {{
      const enabled = gateEnabled && gateEnabled.checked;
      const threshold = (parseFloat(gateThreshold.value || '7') / 100.0);
      const holdMs = parseInt(gateHold.value || '800', 10);

      if (enabled) {{
        if (rms < threshold) {{
          if (silenceStartedAt === null) silenceStartedAt = Date.now();
          if (!gatePaused && (Date.now() - silenceStartedAt) >= holdMs && mediaRecorder.state === 'recording' && mediaRecorder.pause) {{
            try {{
              mediaRecorder.pause();
              gatePaused = true;
              setStatus('Paused (silence)');
            }} catch (e) {{
              console.warn('pause failed', e);
            }}
          }}
        }} else {{
          silenceStartedAt = null;
          if (gatePaused && mediaRecorder.state === 'paused' && mediaRecorder.resume) {{
            try {{
              mediaRecorder.resume();
              gatePaused = false;
              setStatus('Recording…');
            }} catch (e) {{
              console.warn('resume failed', e);
            }}
          }}
        }}
      }}
    }}

    rafId = requestAnimationFrame(draw);
  }}

  async function initMic(deviceId) {{
    if (stream) {{
      for (const t of stream.getTracks()) t.stop();
    }}

    const constraints = deviceId
      ? {{ audio: {{ deviceId: {{ exact: deviceId }} }} }}
      : {{ audio: true }};

    stream = await navigator.mediaDevices.getUserMedia(constraints);
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 2048;
    dataArray = new Uint8Array(analyser.fftSize);
    source = audioCtx.createMediaStreamSource(stream);
    source.connect(analyser);
    rafId = requestAnimationFrame(draw);

    const options = {{ mimeType: 'audio/webm;codecs=opus' }};
    mediaRecorder = MediaRecorder.isTypeSupported(options.mimeType)
      ? new MediaRecorder(stream, options)
      : new MediaRecorder(stream);

    mediaRecorder.ondataavailable = (e) => {{
      if (e.data && e.data.size > 0) chunks.push(e.data);
    }};

    mediaRecorder.onstop = () => {{
      const blob = new Blob(chunks, {{ type: mediaRecorder.mimeType || 'audio/webm' }});
      chunks = [];
      lastBlob = blob;
      saveBtn.disabled = false;
      setStatus('Ready to save');
    }};

    await refreshDevices();
  }}

  async function uploadBlob(blob) {{
    setStatus('Uploading…');
    const fd = new FormData();
    const base = (nameBase.value || 'recording').trim();
    const ext = (blob.type.includes('webm') ? 'webm' : 'bin');
    fd.append('file', blob, `${{base}}.${{ext}}`);
    fd.append('name_base', base);
    const ts = (trimStart.value || '').trim();
    const te = (trimEnd.value || '').trim();
    if (ts) fd.append('trim_start', ts);
    if (te) fd.append('trim_end', te);
    if (autoUploadGcs.checked) {{
      autoGcsIndicator.style.display = 'inline';
      autoGcsIndicator.textContent = '⏳';
      mainAutoGcsIndicator.style.display = 'inline';
      mainAutoGcsIndicator.classList.add('pulse');
    }}
    if (autoTranscribe.checked) {{
      autoTranscribeIndicator.style.display = 'inline';
      autoTranscribeIndicator.textContent = '⏳';
      mainAutoTranscribeIndicator.style.display = 'inline';
      mainAutoTranscribeIndicator.classList.add('pulse');
    }}
    if (autoUploadGcs.checked) fd.append('auto_upload_gcs', '1');
    if (autoTranscribe.checked) fd.append('auto_transcribe', '1');

    const res = await fetch('/api/upload', {{ method: 'POST', body: fd }});
    if (!res.ok) {{
      const txt = await res.text();
      setStatus('Error');
      alert(txt);
      return;
    }}
    const data = await res.json();
    setStatus('Saved');
    lastSaved.textContent = data.mp3_filename || data.original_filename;
    if (typeof lastRecordedMs === 'number') {{
      lastDuration.textContent = `${{fmtTime(lastRecordedMs)}} (${{(lastRecordedMs/1000).toFixed(2)}}s)`;
    }}
    // Auto status feedback
    const autoParts = [];
    if (data.auto_gcs_uploaded) autoParts.push('GCS');
    if (data.auto_transcribed) autoParts.push('Transcribed');
    autoStatus.textContent = autoParts.length ? autoParts.join(' + ') : 'Disabled';

    // Update indicators
    if (autoUploadGcs.checked) {{
      autoGcsIndicator.textContent = data.auto_gcs_uploaded ? '✅' : '❌';
      mainAutoGcsIndicator.classList.remove('pulse');
      mainAutoGcsIndicator.style.display = 'none';
    }}
    if (autoTranscribe.checked) {{
      autoTranscribeIndicator.textContent = data.auto_transcribed ? '✅' : '❌';
      mainAutoTranscribeIndicator.classList.remove('pulse');
      mainAutoTranscribeIndicator.style.display = 'none';
    }}
    links.innerHTML = '';
    if (data.mp3_url) {{
      const a = document.createElement('a');
      a.href = '#';
      a.textContent = 'Download MP3';
      a.addEventListener('click', async (e) => {{
        e.preventDefault();
        await saveWithPicker(data.mp3_url, data.mp3_filename);
      }});
      links.appendChild(a);
      lastMp3Url = data.mp3_url;
      playBtn.disabled = false;
      player.src = data.mp3_url;
      player.style.display = 'block';
    }}
  }}

  function startTimer() {{
    startTs = Date.now();
    timerPill.textContent = '00:00';
    timerId = setInterval(() => {{
      const elapsed = Date.now() - startTs;
      timerPill.textContent = fmtTime(elapsed);
    }}, 200);
  }}

  function stopTimer() {{
    clearInterval(timerId);
    timerId = null;
    timerPill.textContent = '00:00';
  }}

  startBtn.addEventListener('click', async () => {{
    try {{
      if (!mediaRecorder) await initMic(deviceSelect.value);
      setStatus('Recording…');
      startBtn.disabled = true;
      stopBtn.disabled = false;
      playBtn.disabled = true;
      saveBtn.disabled = true;
      recordingActive = true;
      gatePaused = false;
      silenceStartedAt = null;
      mediaRecorder.start();
      startTimer();
    }} catch (err) {{
      console.error(err);
      alert('Microphone init failed: ' + err);
    }}
  }});

  stopBtn.addEventListener('click', () => {{
    try {{
      setStatus('Stopping…');
      stopBtn.disabled = true;
      startBtn.disabled = false;
      stopTimer();
      lastRecordedMs = Date.now() - startTs;
      recordingActive = false;
      mediaRecorder.stop();
    }} catch (err) {{
      console.error(err);
      alert('Stop failed: ' + err);
    }}
  }});

  saveBtn.addEventListener('click', async () => {{
    try {{
      if (!lastBlob) {{
        alert('Nothing to save yet. Record and stop first.');
        return;
      }}
      saveBtn.disabled = true;
      await uploadBlob(lastBlob);
    }} catch (err) {{
      console.error(err);
      setStatus('Error');
      alert('Save failed: ' + err);
      saveBtn.disabled = false;
    }}
  }});

  playBtn.addEventListener('click', () => {{
    if (!lastMp3Url) return;
    player.play();
  }});

  setStatus('Idle');
  lastDuration.textContent = 'None';
  downloadStatus.textContent = 'Not downloaded';

  aboutBtn.addEventListener('click', openAbout);
  aboutCloseBtn.addEventListener('click', closeAbout);
  aboutBackdrop.addEventListener('click', (e) => {{
    if (e.target === aboutBackdrop) closeAbout();
  }});
  settingsBtn.addEventListener('click', openSettings);
  settingsCloseBtn.addEventListener('click', closeSettings);
  settingsBackdrop.addEventListener('click', (e) => {{
    if (e.target === settingsBackdrop) closeSettings();
  }});
  autoUploadGcs.addEventListener('change', () => {{
    if (!autoUploadGcs.checked) autoGcsIndicator.style.display = 'none';
  }});
  autoTranscribe.addEventListener('change', () => {{
    if (!autoTranscribe.checked) autoTranscribeIndicator.style.display = 'none';
  }});
  window.addEventListener('keydown', (e) => {{
    if (e.key === 'Escape') {{
      closeAbout();
      closeSettings();
    }}
  }});

  // Keyboard shortcuts
  window.addEventListener('keydown', async (e) => {{
    if (e.ctrlKey && (e.key === 's' || e.key === 'S')) {{
      e.preventDefault();
      if (!saveBtn.disabled) saveBtn.click();
      return;
    }}

    if (e.code === 'Space') {{
      const tag = (e.target && e.target.tagName) ? e.target.tagName.toLowerCase() : '';
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
      e.preventDefault();
      if (!startBtn.disabled) startBtn.click();
      else if (!stopBtn.disabled) stopBtn.click();
    }}
  }});

  // Player scrub timeline
  player.addEventListener('loadedmetadata', () => {{
    scrub.max = player.duration || 0;
    scrub.value = 0;
    scrubWrap.style.display = 'block';
    scrubLabel.textContent = `00:00 / ${{fmtTime(Math.floor((player.duration || 0) * 1000))}}`;
  }});
  player.addEventListener('timeupdate', () => {{
    if (!isFinite(player.duration) || player.duration <= 0) return;
    scrub.max = player.duration;
    scrub.value = player.currentTime;
    scrubLabel.textContent = `${{fmtTime(Math.floor(player.currentTime * 1000))}} / ${{fmtTime(Math.floor(player.duration * 1000))}}`;
  }});
  scrub.addEventListener('input', () => {{
    player.currentTime = parseFloat(scrub.value || '0');
  }});
</script>
</body>
</html>"""


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "ffmpeg": _ffmpeg_bin()}


@app.post("/api/upload")
async def upload(
    file: UploadFile = File(...),
    name_base: str | None = Form(None),
    trim_start: float | None = Form(None),
    trim_end: float | None = Form(None),
    auto_upload_gcs: str | None = Form(None),
    auto_transcribe: str | None = Form(None),
) -> JSONResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="missing filename")

    base = _safe_stem(name_base or Path(file.filename).stem or "recording")
    stem = _timestamp_name(base)

    original_ext = (Path(file.filename).suffix or ".bin").lower()
    original_name = f"{stem}{original_ext}"
    original_path = RECORDINGS_DIR / original_name

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty upload")
    original_path.write_bytes(content)

    # Convert to MP3
    mp3_name = f"{stem}.mp3"
    mp3_path = RECORDINGS_DIR / mp3_name

    if trim_start is not None and trim_start < 0:
        raise HTTPException(status_code=400, detail="trim_start must be >= 0")
    if trim_end is not None and trim_end < 0:
        raise HTTPException(status_code=400, detail="trim_end must be >= 0")
    if trim_start is not None and trim_end is not None and trim_end <= trim_start:
        raise HTTPException(status_code=400, detail="trim_end must be > trim_start")

    ffmpeg = _ffmpeg_bin()
    ffmpeg_cmd = [
        ffmpeg,
        "-y",
        "-v",
        "error",
        "-i",
        str(original_path),
    ]

    if trim_start is not None:
        ffmpeg_cmd.extend(["-ss", f"{trim_start}"])
    if trim_end is not None:
        duration = trim_end - (trim_start or 0.0)
        ffmpeg_cmd.extend(["-t", f"{duration}"])

    try:
        subprocess.run(
            [
                *ffmpeg_cmd,
                "-vn",
                "-ac",
                "1",
                "-ar",
                "44100",
                "-codec:a",
                "libmp3lame",
                "-qscale:a",
                "3",
                str(mp3_path),
            ],
            check=True,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"ffmpeg not found: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=500, detail=f"ffmpeg failed: {exc}") from exc

    # Auto-upload to GCS if requested
    auto_gcs_uploaded = False
    auto_transcribed = False
    if auto_upload_gcs == "1":
        try:
            from google.cloud import storage as gcs
            client = gcs.Client()
            bucket_name = os.getenv("GOOGLE_CLOUD_BUCKET")
            if bucket_name:
                bucket = client.bucket(bucket_name)
                blob = bucket.blob(mp3_name)
                blob.upload_from_filename(str(mp3_path))
                auto_gcs_uploaded = True
        except ImportError:
            print("Google Cloud Storage library not installed; skipping auto-upload.", file=sys.stderr)
        except OSError as e:
            # Log but don't fail the whole request
            print(f"Auto GCS upload failed: {e}", file=sys.stderr)

    # Auto-transcribe with gc_stt.py if requested
    if auto_transcribe == "1":
        try:
            result = subprocess.run(
                [sys.executable, str(BASE_DIR / "gc_stt.py"), str(mp3_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                auto_transcribed = True
            else:
                print(f"Auto transcription failed: {result.stderr}", file=sys.stderr)
        except (OSError, subprocess.SubprocessError) as e:
            print(f"Auto transcription error: {e}", file=sys.stderr)

    return JSONResponse(
        {
            "original_filename": original_name,
            "mp3_filename": mp3_name,
            "original_url": f"/recordings/{original_name}",
            "mp3_url": f"/recordings/{mp3_name}",
            "auto_gcs_uploaded": auto_gcs_uploaded,
            "auto_transcribed": auto_transcribed,
        }
    )


def main() -> int:
    """Run the dev server.

    Usage:
        .venv/bin/python audio_recorder.py
    """
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit(
            "uvicorn is not installed. Install requirements then re-run."
        ) from exc

    uvicorn.run(
        "audio_recorder:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

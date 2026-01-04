# Google Cloud Speech-to-Text

Transcribe audio files using Google Cloud Speech-to-Text API v2.

Author: Glenn Mossy
Date: Jan 4, 2025

## Prerequisites

- Python 3.12+
- Google Cloud account with billing enabled
- Google Cloud project with Speech-to-Text API enabled
- Google Cloud Storage bucket for audio uploads
- Authenticated Google Cloud SDK with proper permissions
- Microphone for audio recording (for audio_recorder.py)

## Quick Start

```bash
make setup    # Create venv and install dependencies
make login    # Authenticate with Google Cloud
make auth     # Set application default credentials
make run      # Upload audio to GCS and run batch transcription (requires bucket)
```

> **Important:** Run `source .venv/bin/activate` in each new terminal session before using `python` or `make run`, otherwise the `google-cloud-speech` package will not be found.
> This project now uses **long-running recognize**, so full-length audio (>60s) is supported, but the command will wait for the remote operation to finish.

## Manual Setup

### 1. Install Google Cloud SDK

If not already installed:

```bash
tar -xzf google-cloud-cli-darwin-x86_64.tar.gz
./google-cloud-sdk/install.sh
```

After the installer finishes, reload the PATH additions (do this in every new shell before using `gcloud`):

```bash
source "/Volumes/My Book8TB-6TB Partition/Greatlearning/Week8/GoogleCloud_STT/google-cloud-sdk/path.zsh.inc"
source "/Volumes/My Book8TB-6TB Partition/Greatlearning/Week8/GoogleCloud_STT/google-cloud-sdk/completion.zsh.inc"
```

If you added the lines to `~/.zshrc`, you can also run `source ~/.zshrc` to pick them up.

Verify the CLI is reachable and using Python 3.12:

```bash
gcloud --version
gcloud info | grep "Python Version"
```

### 2. Install system dependencies for audio recording

On macOS, you may need to install PortAudio:

```bash
brew install portaudio
```

### 3. Create Python Environment

Using uv (recommended):

```bash
uv venv --python 3.12.11 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

Or using pip:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Google Cloud Authentication

Initialize gcloud (first time only):

```bash
gcloud init
```

Login and set application default credentials:

```bash
gcloud auth login
gcloud auth application-default login
```

### 4. Enable Speech-to-Text API

```bash
gcloud services enable speech.googleapis.com
```

### 5. Set Your Project

```bash
export GOOGLE_CLOUD_PROJECT=your-project-id
```

Or create a `.env` file with your configuration:

```bash
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_BUCKET=your-bucket-name
```

To find your project ID:

```bash
gcloud projects list
```

### 6. Prepare a Cloud Storage Bucket

You must provide a bucket (same region as your recognizer recommended) for audio uploads:

```bash
gsutil mb -p "$GOOGLE_CLOUD_PROJECT" gs://my-speech-bucket-$(date +%s)
export GOOGLE_CLOUD_BUCKET=my-speech-bucket-$(date +%s)
```

Grant yourself permission if needed:

```bash
gsutil iam ch user:you@example.com:objectAdmin gs://my-speech-bucket-$(date +%s)
```

## Usage

```bash
source .venv/bin/activate
source "/Volumes/My Book8TB-6TB Partition/Greatlearning/Week8/GoogleCloud_STT/google-cloud-sdk/path.zsh.inc"
export GOOGLE_CLOUD_PROJECT=your-project-id
export GOOGLE_CLOUD_BUCKET=my-speech-bucket
python gc_stt.py
```

Or specify a bucket per run:

```bash
python gc_stt.py --bucket my-speech-bucket /path/to/audio.mp3
```

## Files

- `gc_stt.py` - Main transcription script
- `audio_recorder.py` - Audio recording utility (FastAPI web app)
- `apple_history.mp3` - Sample audio file
- `requirements.txt` - Python dependencies
- `Makefile` - Automation commands

Recordings created by `audio_recorder.py` are written to `recordings/`.

## Audio Recorder Utility

The project includes two audio recording utilities:

1. `audio_recorder.py` - Browser-based recorder (FastAPI)
1. `cli_audio_recorder.py` - Command-line interface for recording audio

Both applications:

- Record audio from your system's default microphone
- Save recordings with timestamped filenames (e.g., `recording_2025-01-04_15-30-45.wav`)
- Attempt to convert recordings to MP3 format

### Browser (FastAPI) Version

This version uses the browser microphone APIs (so it avoids Tcl/Tk issues on macOS).

To run the recorder:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python audio_recorder.py
```

Open:

```text
http://127.0.0.1:8000
```

Features:

- Start/stop recording in the browser
- Live level meter and oscilloscope-style trace
- Upload to Python backend and save as MP3
- Playback + download from the web page

### Command-Line Version

To run the command-line audio recorder:

```bash
source .venv/bin/activate
python cli_audio_recorder.py
```

Features:

- Enter recording duration when prompted
- Press Ctrl+C to stop recording early

### Note on MP3 Conversion

The applications convert recordings to MP3 format using ffmpeg. This repo supports a local `./ffmpeg` binary placed next to the scripts. If `./ffmpeg` is not present, it will fall back to `ffmpeg` on your PATH.

1. Install Homebrew (if not already installed):

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

1. Install ffmpeg:

```bash
brew install ffmpeg
```

## Troubleshooting

### "Could not automatically determine credentials"

Run: `gcloud auth application-default login`

### "Speech-to-Text API has not been enabled"

Run: `gcloud services enable speech.googleapis.com`

### "Permission denied"

Ensure your account has the `Cloud Speech Client` role in IAM.

### Remove Credentials (Optional)

```bash
make revoke-app-default   # Remove application default credentials
make revoke-user          # Revoke gcloud user credentials
```

Or run the raw commands:

```bash
gcloud auth application-default revoke
gcloud auth revoke
```

### Batch Transcription Notes

- The script uploads the audio file to Cloud Storage, then calls `SpeechClient.batch_recognize`.
- By default, transcripts are returned inline; for large jobs you can switch to GCS output in code.
- Keep your bucket and recognizer in the same region to avoid latency/egress charges.
- If you encounter "internal error" messages, try running the script again as it might be a temporary service issue.

## Links

- [Google Cloud Speech-to-Text Documentation](https://cloud.google.com/speech-to-text/docs)
- [Python Client Library](https://cloud.google.com/python/docs/reference/speech/latest)

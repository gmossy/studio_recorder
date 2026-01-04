"""Command-line audio recorder for macOS.

This application provides a simple command-line interface to record audio from the 
microphone and save it as an MP3 file with timestamped filenames.

Author: Glenn Mossy
Date: Jan 4, 2025
"""

import sounddevice as sd
import numpy as np
import datetime
import os
import time
from pydub import AudioSegment
from scipy.io.wavfile import write as wavwrite


def record_audio(duration=10, rate=44100, channels=1, dtype=np.int16):
    """Record audio from the microphone."""
    print(f"Recording for {duration} seconds...")
    print("Press Ctrl+C to stop recording early")
    
    try:
        # Record audio
        audio_data = sd.rec(int(duration * rate), samplerate=rate, 
                           channels=channels, dtype=dtype)
        sd.wait()  # Wait until recording is finished
        return audio_data
    except KeyboardInterrupt:
        print("\nRecording stopped by user")
        return None


def save_recording(audio_data, rate=44100):
    """Save the recorded audio as an MP3 file."""
    if audio_data is None:
        return
        
    try:
        # Generate filename with timestamp
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        wav_filename = f"recording_{timestamp}.wav"
        mp3_filename = f"recording_{timestamp}.mp3"
        
        # Save as WAV first
        wavwrite(wav_filename, rate, audio_data)
        
        # Convert to MP3
        audio = AudioSegment.from_wav(wav_filename)
        audio.export(mp3_filename, format="mp3")
        
        # Remove temporary WAV file
        os.remove(wav_filename)
        
        print(f"Recording saved as {mp3_filename}")
        return mp3_filename
        
    except Exception as e:
        print(f"Error saving recording: {e}")
        return None


def main():
    print("Audio Recorder (Command-Line Version)")
    print("=====================================")
    
    # Get recording duration from user
    try:
        duration_input = input("Enter recording duration in seconds (default 10): ")
        if duration_input.strip() == "":
            duration = 10
        else:
            duration = int(duration_input)
    except (ValueError, EOFError):
        print("Invalid input or no input provided, using default duration of 10 seconds")
        duration = 10
    
    # Record audio
    audio_data = record_audio(duration=duration)
    
    # Save recording
    if audio_data is not None:
        filename = save_recording(audio_data)
        if filename:
            print(f"Successfully saved recording: {filename}")
        else:
            print("Failed to save recording")
    else:
        print("No audio recorded")


if __name__ == "__main__":
    main()

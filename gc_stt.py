"""Google Cloud Speech-to-Text batch transcription script.

Author: Glenn Mossy
Date: Jan 4, 2025
"""

import argparse
import os
from uuid import uuid4

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

from google.cloud import storage
from google.cloud.speech_v2 import SpeechClient
from google.cloud.speech_v2.types import cloud_speech

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
DEFAULT_BUCKET = os.getenv("GOOGLE_CLOUD_BUCKET")


def upload_to_gcs(local_path: str, bucket_name: str, project_id: str) -> str:
    """Upload a local audio file to Cloud Storage and return the gs:// URI."""
    client = storage.Client(project=project_id)
    bucket = client.bucket(bucket_name)
    if not bucket.exists():
        raise RuntimeError(
            f"Bucket '{bucket_name}' does not exist or is not accessible in project '{project_id}'."
        )

    blob_name = f"uploads/{uuid4()}_{os.path.basename(local_path)}"
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(local_path)
    return f"gs://{bucket_name}/{blob_name}"


def transcribe_long_audio(input_file: str, bucket_name: str) -> cloud_speech.BatchRecognizeResponse:
    """Transcribe long audio using BatchRecognize with inline results."""
    gcs_uri = upload_to_gcs(input_file, bucket_name, PROJECT_ID)
    print(f"Uploaded audio to {gcs_uri}")

    client = SpeechClient()

    config = cloud_speech.RecognitionConfig(
        auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
        language_codes=["en-US"],
        model="long",
    )

    file_metadata = cloud_speech.BatchRecognizeFileMetadata(
        uri=gcs_uri,
    )

    output_config = cloud_speech.RecognitionOutputConfig(
        inline_response_config=cloud_speech.InlineOutputConfig()
    )

    request = cloud_speech.BatchRecognizeRequest(
        recognizer=f"projects/{PROJECT_ID}/locations/global/recognizers/_",
        config=config,
        files=[file_metadata],
        recognition_output_config=output_config,
    )

    operation = client.batch_recognize(request=request)
    print("Waiting for transcription operation to complete...")
    response = operation.result(timeout=3600)

    if not response.results:
        raise RuntimeError("No transcription results returned.")

    file_key, file_result = next(iter(response.results.items()))
    if file_result.error and file_result.error.code:
        raise RuntimeError(f"Transcription failed for {file_key}: {file_result.error.message}")

    inline_result = file_result.inline_result
    if not inline_result or not inline_result.transcript.results:
        print("No transcript text returned.")
        return response

    for idx, result in enumerate(inline_result.transcript.results, start=1):
        if result.alternatives:
            print(f"[Segment {idx}] {result.alternatives[0].transcript}")

    return response


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Google Cloud Speech-to-Text batch transcription"
    )
    parser.add_argument(
        "audio_file",
        nargs="?",
        default="apple_history.mp3", 
        help="Path to local audio file"
    )
    parser.add_argument(
        "--bucket",
        default=DEFAULT_BUCKET,
        help="Cloud Storage bucket name (or set GOOGLE_CLOUD_BUCKET)",
    )
    args = parser.parse_args()

    if not PROJECT_ID:
        raise SystemExit("Error: GOOGLE_CLOUD_PROJECT environment variable not set.")

    if not args.bucket:
        raise SystemExit(
            "Error: specify a bucket via --bucket or set GOOGLE_CLOUD_BUCKET environment variable."
        )

    print(f"Transcribing: {args.audio_file}")
    print(f"Using project: {PROJECT_ID}")
    print(f"Uploading to bucket: {args.bucket}")

    transcribe_long_audio(args.audio_file, args.bucket)

"""Media adapter — wraps the local ffmpeg/ffprobe tools and B2 downloads.

External tool calls live in the repo layer like any other adapter. ffmpeg is
a system prerequisite (see README / scripts/doctor.mjs).
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path

from botocore.exceptions import ClientError

from app.config import settings
from app.repo.b2_client import get_s3_client

logger = logging.getLogger(__name__)


def download_to_temp(key: str, suffix: str = "") -> str:
    """Stream an object from B2 to a temp file and return its path."""
    client = get_s3_client()
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        client.download_file(settings.b2_bucket_name, key, path)
    except ClientError as e:
        raise RuntimeError(f"B2 download failed for '{key}': {e}") from e
    return path


def extract_audio(video_path: str) -> str:
    """Extract a mono 16 kHz track suitable for transcription. Returns a path."""
    out = str(Path(tempfile.mkdtemp()) / "audio.m4a")
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "aac", out,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed: {proc.stderr[-500:]}")
    return out


def probe_duration(path: str) -> float | None:
    """Return media duration in seconds via ffprobe, or None on failure."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.warning("ffprobe failed: %s", proc.stderr[-200:])
        return None
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return None

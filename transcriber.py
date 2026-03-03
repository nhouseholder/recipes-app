"""
Video Transcriber
Uses OpenAI's Whisper (runs locally, free) to transcribe video audio.
"""

import os
import subprocess
import whisper
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
VIDEOS_DIR = DATA_DIR / "videos"

_model = None
_model_size = None


def get_model(model_size: str = "base"):
    """Load Whisper model (cached after first load; reloads if size changes)."""
    global _model, _model_size
    if _model is None or _model_size != model_size:
        print(f"[Whisper] Loading '{model_size}' model (first time may download)...")
        _model = whisper.load_model(model_size)
        _model_size = model_size
        print("[Whisper] Model loaded.")
    return _model


def extract_audio(video_path: str) -> str:
    """Extract audio from video file using ffmpeg."""
    video_path = Path(video_path)
    audio_path = video_path.with_suffix('.wav')

    if audio_path.exists():
        return str(audio_path)

    print(f"[Audio] Extracting audio from {video_path.name}...")
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-i", str(video_path),
                "-vn",  # No video
                "-acodec", "pcm_s16le",  # WAV format
                "-ar", "16000",  # 16kHz sample rate (Whisper optimal)
                "-ac", "1",  # Mono
                "-y",  # Overwrite
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            print(f"[Audio] ffmpeg warning: {result.stderr[:200]}")
            # Try without specific codec
            subprocess.run(
                ["ffmpeg", "-i", str(video_path), "-vn", "-y", str(audio_path)],
                capture_output=True, timeout=60,
            )
    except FileNotFoundError:
        raise Exception(
            "ffmpeg not found. Install it:\n"
            "  macOS: brew install ffmpeg\n"
            "  Ubuntu: sudo apt install ffmpeg\n"
            "  Windows: download from ffmpeg.org"
        )

    return str(audio_path)


def transcribe_video(video_path: str, model_size: str = "base") -> dict:
    """
    Transcribe a video file.
    Returns dict with 'text' (full transcript) and 'segments' (timestamped).
    """
    video_path = Path(video_path)

    if not video_path.exists():
        # Try to find it in videos dir
        video_path = VIDEOS_DIR / video_path.name
        if not video_path.exists():
            return {"text": "", "segments": [], "error": f"Video not found: {video_path}"}

    print(f"[Whisper] Transcribing {video_path.name}...")

    # Extract audio first
    try:
        audio_path = extract_audio(str(video_path))
    except Exception as e:
        # If ffmpeg fails, try giving the video directly to Whisper
        audio_path = str(video_path)

    # Transcribe
    model = get_model(model_size)
    result = model.transcribe(
        audio_path,
        language="en",  # Assume English; remove for auto-detect
        fp16=False,  # CPU compatibility
    )

    transcript = {
        "text": result["text"].strip(),
        "segments": [
            {
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"].strip(),
            }
            for seg in result.get("segments", [])
        ],
    }

    print(f"[Whisper] Transcribed {video_path.name}: {len(transcript['text'])} chars")

    # Clean up wav file to save space
    wav_path = video_path.with_suffix('.wav')
    if wav_path.exists():
        os.remove(wav_path)

    return transcript


def transcribe_all_videos(model_size: str = "base") -> dict[str, dict]:
    """
    Transcribe all videos in the videos directory.
    Returns dict mapping video filename to transcript.
    """
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    transcripts = {}
    video_extensions = ('.mp4', '.mov', '.avi', '.mkv', '.webm')

    video_files = []
    for ext in video_extensions:
        video_files.extend(VIDEOS_DIR.glob(f"*{ext}"))

    if not video_files:
        print("[Whisper] No videos found in data/videos/ directory")
        return {}

    print(f"[Whisper] Found {len(video_files)} videos to transcribe")

    for i, video in enumerate(sorted(video_files)):
        print(f"\n[{i + 1}/{len(video_files)}] Processing {video.name}")
        transcript = transcribe_video(str(video), model_size)
        transcripts[video.stem] = transcript

    return transcripts

"""
Download audio from URLs (YouTube, podcasts, and 1000+ other sites via yt-dlp).
Returns the local path to the extracted audio file and the video title.
"""

import re
import tempfile
from pathlib import Path

import yt_dlp


def _safe_filename(title: str, max_length: int = 80) -> str:
    """Strip characters that are invalid in filenames."""
    safe = re.sub(r'[<>:"/\\|?*]', "", title)
    safe = re.sub(r"\s+", " ", safe).strip()
    return safe[:max_length]


def download_audio(url: str, output_dir: Path) -> tuple[Path, str]:
    """
    Download audio from a URL and convert to MP3.

    Args:
        url:        Any URL supported by yt-dlp (YouTube, Vimeo, podcasts, etc.)
        output_dir: Directory where the MP3 will be saved.

    Returns:
        (audio_path, title) — path to the MP3 file and the video/episode title.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Fetch metadata first so we can build a clean filename
    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        info = ydl.extract_info(url, download=False)

    title = info.get("title") or info.get("id") or "audio"
    safe_title = _safe_filename(title)
    audio_path = output_dir / f"{safe_title}.mp3"

    ydl_opts = {
        "format": "bestaudio/best",
        # Use video ID as the intermediate filename to avoid yt-dlp's own sanitization
        "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",  # 128 kbps is plenty for speech
            }
        ],
        "quiet": False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # Rename from <id>.mp3 to <safe_title>.mp3
    video_id = info.get("id", "audio")
    raw_path = output_dir / f"{video_id}.mp3"
    if raw_path.exists():
        raw_path.rename(audio_path)
    else:
        # Fallback: grab whatever mp3 landed in the dir
        mp3_files = list(output_dir.glob("*.mp3"))
        if not mp3_files:
            raise FileNotFoundError(f"No MP3 found in {output_dir} after download")
        mp3_files[0].rename(audio_path)

    return audio_path, title

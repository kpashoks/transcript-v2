"""
Transcript cache — avoids re-uploading to AssemblyAI for files already processed.

Cache keys:
  - URLs        → SHA-256 of the URL string
  - Local files → SHA-256 of the file content

Cached data is stored as JSON in the cache/ directory alongside the project.
"""

import hashlib
import json
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)


def cache_key_for_url(url: str) -> str:
    """Stable cache key for a URL."""
    return hashlib.sha256(url.encode()).hexdigest()


def cache_key_for_file(file_path: Path) -> str:
    """Stable cache key based on the file's content hash."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65_536), b""):
            h.update(chunk)
    return h.hexdigest()


def load(key: str) -> dict | None:
    """
    Return cached transcript data for the given key, or None if not found.

    Returned dict shape:
        {
            "title":      str,
            "utterances": list[dict],   # same format as transcriber.transcribe()
        }
    """
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            # Corrupted cache file — treat as miss
            path.unlink(missing_ok=True)
    return None


def save(key: str, utterances: list[dict], title: str) -> None:
    """Persist transcript utterances and title under the given cache key."""
    path = CACHE_DIR / f"{key}.json"
    path.write_text(
        json.dumps({"title": title, "utterances": utterances}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def clear(key: str) -> bool:
    """Delete a single cache entry. Returns True if it existed."""
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        path.unlink()
        return True
    return False

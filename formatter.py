"""
Format transcripts and summaries into clean, readable files.
Outputs both Markdown (.md) and plain text (.txt) versions.
"""

import re
from pathlib import Path


def _ms_to_timestamp(ms: int) -> str:
    total = ms // 1000
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


def _safe_filename(title: str, max_length: int = 60) -> str:
    safe = re.sub(r'[<>:"/\\|?*]', "", title)
    safe = re.sub(r"\s+", " ", safe).strip()
    return safe[:max_length]


def format_transcript(utterances: list[dict], speaker_names: dict[str, str]) -> str:
    """
    Render speaker-labeled utterances as clean, readable dialogue.

    Consecutive utterances from the same speaker are grouped together.
    Each speaker turn is preceded by a blank line for readability.
    """
    lines = []
    prev_speaker = None

    for u in utterances:
        name = speaker_names.get(u["speaker"], f"Speaker {u['speaker']}")
        ts = _ms_to_timestamp(u["start_ms"])

        if u["speaker"] != prev_speaker:
            lines.append("")  # visual break between speakers
            lines.append(f"[{ts}]  {name}:")
            prev_speaker = u["speaker"]

        # Indent the text under the speaker label
        lines.append(f"    {u['text']}")

    return "\n".join(lines).strip()


def _markdown_to_plain(md: str) -> str:
    """
    Convert Markdown summary to readable plain text.
    Strips ** bold **, ## headings markers, and inline backticks.
    """
    text = md
    # Remove bold/italic markers
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    # Convert ## headings to uppercase lines with underlines
    def heading(m):
        level = len(m.group(1))
        title = m.group(2).strip()
        underline = ("=" if level <= 2 else "-") * len(title)
        return f"\n{title}\n{underline}"
    text = re.sub(r"^(#{1,6})\s+(.+)$", heading, text, flags=re.MULTILINE)
    # Remove inline code backticks
    text = re.sub(r"`(.+?)`", r"\1", text)
    # Clean up excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def save_outputs(
    title: str,
    transcript_text: str,
    summary_text: str,
    output_dir: Path,
) -> tuple[Path, Path, Path, Path]:
    """
    Write transcript and summary as both .md and .txt files.

    Returns (transcript_md, transcript_txt, summary_md, summary_txt).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    base = _safe_filename(title)

    transcript_md_path = output_dir / f"{base}_transcript.md"
    transcript_txt_path = output_dir / f"{base}_transcript.txt"
    summary_md_path = output_dir / f"{base}_summary.md"
    summary_txt_path = output_dir / f"{base}_summary.txt"

    # --- Transcript ---
    transcript_md = f"# Transcript: {title}\n\n{transcript_text}"
    transcript_md_path.write_text(transcript_md, encoding="utf-8")
    transcript_txt_path.write_text(transcript_text, encoding="utf-8")

    # --- Summary ---
    summary_plain = _markdown_to_plain(summary_text)
    summary_md_path.write_text(f"# Summary: {title}\n\n{summary_text}", encoding="utf-8")
    summary_txt_path.write_text(f"Summary: {title}\n\n{summary_plain}", encoding="utf-8")

    return transcript_md_path, transcript_txt_path, summary_md_path, summary_txt_path

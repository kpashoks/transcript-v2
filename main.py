#!/usr/bin/env python3
"""
transcript-v2 — Transcribe, analyze, and summarize audio/video content.

Handles YouTube URLs, podcast URLs, and local audio/video files.
Uses AssemblyAI for speaker-diarized transcription and Claude for analysis.

USAGE
-----
  # YouTube or any URL:
  python main.py "https://www.youtube.com/watch?v=VIDEO_ID"

  # Local file:
  python main.py /path/to/recording.mp3

  # With speaker count hint (improves diarization accuracy):
  python main.py "https://..." --speakers 3

  # With optional context to improve speaker identification and summary:
  python main.py "https://..." --context "Molly is a Stripe recruiter. Ashok is the candidate receiving interview feedback."

  # Custom output directory:
  python main.py "https://..." --output-dir /path/to/folder

OUTPUT
------
  Four files are saved to the output directory:
    <title>_transcript.md   — full timestamped transcript (Markdown)
    <title>_transcript.txt  — full timestamped transcript (plain text)
    <title>_summary.md      — key takeaways + themes (Markdown)
    <title>_summary.txt     — key takeaways + themes (plain text)
"""

import argparse
import shutil
import sys
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Transcribe and summarize audio/video with speaker identification.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "source",
        help="YouTube/podcast URL or path to a local audio/video file.",
    )
    parser.add_argument(
        "--speakers",
        type=int,
        default=None,
        metavar="N",
        help="Expected number of speakers (optional). Improves diarization accuracy.",
    )
    parser.add_argument(
        "--context",
        type=str,
        default=None,
        metavar="TEXT",
        help=(
            "Optional background context about the recording. "
            "Describe who the speakers are, their roles, and what the conversation is about. "
            "This improves speaker identification and summary quality. "
            'Example: "Molly is a Stripe recruiter. Ashok is the candidate receiving interview feedback."'
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help="Directory for output files. Defaults to transcript-v2/output/.",
    )
    return parser.parse_args()


def is_url(source: str) -> bool:
    return source.startswith("http://") or source.startswith("https://")


def main() -> None:
    args = parse_args()

    # Lazy import so config errors surface cleanly
    from config import OUTPUT_DIR

    output_dir = args.output_dir or OUTPUT_DIR

    # ------------------------------------------------------------------ #
    # Step 1 — Acquire audio                                               #
    # ------------------------------------------------------------------ #
    if is_url(args.source):
        print("\n[1/4] Downloading audio...")
        from downloader import download_audio

        tmp_dir = Path(tempfile.mkdtemp(prefix="transcript_v2_"))
        try:
            audio_path, title = download_audio(args.source, tmp_dir)
            print(f"      Title : {title}")
            print(f"      File  : {audio_path.name}")

            # ---------------------------------------------------------- #
            # Steps 2–4 run while the temp audio file still exists        #
            # ---------------------------------------------------------- #
            utterances, speaker_names, summary = _process(
                audio_path, title, args.speakers, args.context
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    else:
        audio_path = Path(args.source)
        if not audio_path.exists():
            print(f"Error: file not found — {args.source}", file=sys.stderr)
            sys.exit(1)

        title = audio_path.stem
        print(f"\n[1/4] Using local file: {audio_path.name}")
        utterances, speaker_names, summary = _process(
            audio_path, title, args.speakers, args.context
        )

    # ------------------------------------------------------------------ #
    # Step 4 — Format and save                                            #
    # ------------------------------------------------------------------ #
    print("\n[4/4] Saving output files...")
    from formatter import format_transcript, save_outputs

    transcript_text = format_transcript(utterances, speaker_names)
    paths = save_outputs(title, transcript_text, summary, output_dir)

    print(f"\nDone! Files saved to: {output_dir}\n")
    for p in paths:
        print(f"  {p.name}")
    print()


def _process(
    audio_path: Path, title: str, num_speakers: int | None, context: str | None
) -> tuple[list[dict], dict[str, str], str]:
    """Transcribe → identify speakers → summarize. Returns raw data."""

    # Step 2 — Transcribe
    print("\n[2/4] Transcribing with speaker diarization...")
    print("      (This can take several minutes for long recordings.)")
    from transcriber import transcribe

    utterances = transcribe(audio_path, num_speakers=num_speakers)
    n_speakers = len(set(u["speaker"] for u in utterances))
    print(f"      Done — {len(utterances):,} utterances, {n_speakers} speakers detected.")

    if context:
        print(f"      Context: {context}")

    # Step 3 — Identify speakers + summarize
    print("\n[3/4] Analyzing with Claude...")
    from analyzer import identify_speakers, summarize

    speaker_names = identify_speakers(utterances, context=context)
    print(f"      Speakers: {speaker_names}")

    summary = summarize(utterances, speaker_names, title, context=context)

    return utterances, speaker_names, summary


if __name__ == "__main__":
    main()

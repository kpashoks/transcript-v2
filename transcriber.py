"""
Transcribe audio using AssemblyAI with speaker diarization.

AssemblyAI automatically detects the number of speakers if `num_speakers`
is not provided, but giving it a hint improves accuracy for panel discussions.
"""

from pathlib import Path

import assemblyai as aai

from config import ASSEMBLYAI_API_KEY


def transcribe(audio_path: Path, num_speakers: int = None) -> list[dict]:
    """
    Transcribe audio with speaker diarization.

    Args:
        audio_path:   Path to the local audio file (MP3, WAV, M4A, etc.)
        num_speakers: Expected number of speakers. None = auto-detect.

    Returns:
        List of utterances, each a dict:
            {
                "speaker":  "A" | "B" | "C" ...,
                "text":     "What the speaker said",
                "start_ms": 12400,   # start time in milliseconds
                "end_ms":   15800,
            }
    """
    aai.settings.api_key = ASSEMBLYAI_API_KEY

    config = aai.TranscriptionConfig(
        speech_models=["universal-2"],
        speaker_labels=True,
        speakers_expected=num_speakers,  # None = let AssemblyAI decide
    )

    transcriber = aai.Transcriber()

    print(f"  Uploading {audio_path.name} to AssemblyAI...")
    transcript = transcriber.transcribe(str(audio_path), config=config)

    if transcript.status == aai.TranscriptStatus.error:
        raise RuntimeError(f"AssemblyAI transcription failed: {transcript.error}")

    utterances = [
        {
            "speaker": u.speaker,
            "text": u.text,
            "start_ms": u.start,
            "end_ms": u.end,
        }
        for u in transcript.utterances
    ]

    return utterances

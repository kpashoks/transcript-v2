"""
Analyze transcripts using an AI provider (Anthropic Claude or OpenAI GPT-4o):
  1. Identify speaker names from conversational context.
  2. Generate a structured summary with timestamped key takeaways.

For long transcripts the summarizer uses a map→merge strategy:
  - Map:   each chunk is summarized into structured notes with timestamps.
  - Merge: all chunk notes are synthesized into the final document.

This guarantees full coverage regardless of transcript length.

Switch providers by setting AI_PROVIDER in .env to "anthropic" or "openai".
"""

import json
import re

from config import (
    AI_PROVIDER,
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
)

# ---------------------------------------------------------------------------
# Client initialisation
# ---------------------------------------------------------------------------

if AI_PROVIDER == "openai":
    from openai import OpenAI
    _openai_client = OpenAI(api_key=OPENAI_API_KEY)
else:
    import anthropic
    _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Max chars per chunk sent to the model.
# Claude has a 200K-token window (~800K chars) but we stay conservative to
# leave plenty of room for the prompt overhead and response.
# GPT-4o has a 128K-token window (~512K chars) — 120K chars is safe for both.
CHUNK_CHARS = 120_000

# Number of utterances to repeat at the start of each new chunk so the model
# has context about the conversation that just ended.
OVERLAP_UTTERANCES = 5


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _chat(prompt: str, max_tokens: int) -> str:
    """Send a prompt to the active AI provider and return the text response."""
    if AI_PROVIDER == "openai":
        r = _openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return r.choices[0].message.content
    else:
        r = _anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return r.content[0].text


def _ms_to_timestamp(ms: int) -> str:
    total = ms // 1000
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


def _build_transcript_text(utterances: list[dict], speaker_names: dict[str, str]) -> str:
    lines = []
    for u in utterances:
        name = speaker_names.get(u["speaker"], f"Speaker {u['speaker']}")
        ts = _ms_to_timestamp(u["start_ms"])
        lines.append(f"[{ts}] {name}: {u['text']}")
    return "\n".join(lines)


def _split_into_chunks(
    utterances: list[dict],
    speaker_names: dict[str, str],
) -> list[list[dict]]:
    """
    Split utterances into chunks whose rendered text fits within CHUNK_CHARS.

    Each chunk overlaps with the previous one by OVERLAP_UTTERANCES utterances
    so the model always has context at the start of a new chunk.
    """
    chunks: list[list[dict]] = []
    current: list[dict] = []
    current_chars = 0

    def _line_len(u: dict) -> int:
        name = speaker_names.get(u["speaker"], f"Speaker {u['speaker']}")
        return len(f"[{_ms_to_timestamp(u['start_ms'])}] {name}: {u['text']}\n")

    for u in utterances:
        llen = _line_len(u)

        if current_chars + llen > CHUNK_CHARS and current:
            chunks.append(current)
            # Carry the tail of the previous chunk forward for continuity
            overlap = current[-OVERLAP_UTTERANCES:]
            current = list(overlap)
            current_chars = sum(_line_len(x) for x in current)

        current.append(u)
        current_chars += llen

    if current:
        chunks.append(current)

    return chunks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def identify_speakers(utterances: list[dict], context: str | None = None) -> dict[str, str]:
    """
    Ask the AI to identify real speaker names from conversational cues.

    Samples utterances spread across the full transcript so the model sees
    introductions, name mentions, and topic shifts — not just the opening minutes.

    If the user supplies a context string (e.g. "Molly is a recruiter, Ashok is the
    candidate"), that is included in the prompt to help ground the identification.

    Returns a mapping like {"A": "Molly", "B": "Ashok"}.
    """
    speakers = sorted(set(u["speaker"] for u in utterances))

    step = max(1, len(utterances) // 60)
    sample = utterances[::step][:60]

    sample_text = "\n".join(
        f"[{_ms_to_timestamp(u['start_ms'])}] Speaker {u['speaker']}: {u['text']}"
        for u in sample
    )

    context_block = (
        f"\nBackground context provided by the user:\n{context}\n"
        if context
        else ""
    )

    prompt = f"""I have a transcript of a conversation or panel discussion.
The speakers are labeled: {', '.join(f'Speaker {s}' for s in speakers)}.
{context_block}
Below is a sample of utterances taken from throughout the full transcript:

{sample_text}

Your task: identify the real name of each speaker.

Look for these cues:
- Background context provided above (treat this as the most reliable source)
- Direct address ("Thanks, John", "What do you think, Sarah?")
- Self-introduction ("I'm Dr. Peter Attia...")
- Host introductions ("My guest today is...")
- Role/affiliation mentions that narrow it down

Rules:
- Prioritise the user-provided context above all other cues.
- If you cannot identify a name with confidence, use a descriptive label such as "Host", "Guest 1", or "Moderator".
- Do NOT guess names you are not confident about.

Respond with ONLY a valid JSON object. No explanation, no markdown fences.
Example: {{"A": "Molly", "B": "Ashok"}}

JSON:"""

    raw = _chat(prompt, max_tokens=300).strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return {s: f"Speaker {s}" for s in speakers}


def summarize(
    utterances: list[dict],
    speaker_names: dict[str, str],
    title: str,
    context: str | None = None,
) -> str:
    """
    Generate a structured summary with key takeaways and timestamps.

    Short transcripts  (<= CHUNK_CHARS): single-pass analysis.
    Long transcripts   (>  CHUNK_CHARS): map→merge — each chunk is analysed
                       separately, then all notes are merged into one document.
    """
    full_text = _build_transcript_text(utterances, speaker_names)
    participant_list = ", ".join(speaker_names.values())
    context_block = (
        f"\nBackground context provided by the user:\n{context}\n"
        if context
        else ""
    )

    if len(full_text) <= CHUNK_CHARS:
        return _summarize_single(full_text, title, participant_list, context_block)

    # --- Map → Merge ---
    chunks = _split_into_chunks(utterances, speaker_names)
    n = len(chunks)
    total_chars = len(full_text)
    print(
        f"  Transcript is {total_chars:,} chars — "
        f"splitting into {n} chunks for full coverage."
    )

    chunk_notes: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        print(f"  Summarizing chunk {i}/{n}...")
        chunk_text = _build_transcript_text(chunk, speaker_names)
        notes = _summarize_chunk(chunk_text, i, n, title, participant_list, context_block)
        chunk_notes.append(notes)

    print(f"  Merging {n} chunks into final summary...")
    return _merge_summaries(chunk_notes, title, participant_list, context_block)


# ---------------------------------------------------------------------------
# Internal summarization helpers
# ---------------------------------------------------------------------------

def _summarize_single(
    transcript_text: str,
    title: str,
    participant_list: str,
    context_block: str,
) -> str:
    """Single-pass full analysis for transcripts that fit in one chunk."""
    prompt = f"""You are analyzing the transcript of a recorded discussion titled:
"{title}"

Participants: {participant_list}
{context_block}
--- TRANSCRIPT START ---
{transcript_text}
--- TRANSCRIPT END ---

Produce a structured analysis with the following sections:

## Overview
2–3 sentences describing what this conversation is about and its general tone.

## Participants
One line per person: their name, role or background (if evident), and their general stance in this discussion.

## Key Takeaways
List 10–20 of the most important points, arguments, or insights raised in this conversation.
For each takeaway:
- State it clearly in 2–4 sentences.
- Note who made the point.
- Include the timestamp [HH:MM:SS] where it was first discussed.

Format each as:
**N. [HH:MM:SS] — Short title of the point**
Body text here. (Speaker Name)

## Main Themes
List 3–6 overarching themes, each with the approximate time range where it is primarily discussed.
Format: **Theme name** [HH:MM:SS – HH:MM:SS]: Brief description.

## Notable Agreements & Disagreements
Highlight 2–5 moments where speakers meaningfully agreed or disagreed.
Include the timestamp and a one-sentence description of what was at stake.

Use clean markdown formatting throughout."""

    return _chat(prompt, max_tokens=5000)


def _summarize_chunk(
    chunk_text: str,
    chunk_num: int,
    total_chunks: int,
    title: str,
    participant_list: str,
    context_block: str,
) -> str:
    """
    Summarize one chunk into structured notes with timestamps.
    These notes are consumed by _merge_summaries(), not shown to the user directly.
    """
    prompt = f"""You are analyzing segment {chunk_num} of {total_chunks} of a recorded discussion titled:
"{title}"

Participants: {participant_list}
{context_block}
--- SEGMENT {chunk_num}/{total_chunks} START ---
{chunk_text}
--- SEGMENT {chunk_num}/{total_chunks} END ---

Extract every significant point, argument, fact, insight, agreement, or disagreement from this segment.
Be thorough — these notes will be merged with notes from other segments to form the final analysis,
so it is better to include too much than too little.

For each item write:
  [HH:MM:SS] — Title: 2–3 sentence description. (Speaker Name)

Also add a one-line note at the end if the segment ends mid-topic so the merge pass can handle continuity.

Output ONLY the numbered list. No headings, no preamble."""

    return _chat(prompt, max_tokens=3000)


def _merge_summaries(
    chunk_notes: list[str],
    title: str,
    participant_list: str,
    context_block: str,
) -> str:
    """
    Merge per-chunk notes into a single cohesive structured analysis.
    Timestamps in the notes come from the original transcript so they remain accurate.
    """
    all_notes = "\n\n".join(
        f"=== SEGMENT {i + 1} NOTES ===\n{notes}"
        for i, notes in enumerate(chunk_notes)
    )

    prompt = f"""You are producing the final structured analysis of a recorded discussion titled:
"{title}"

Participants: {participant_list}
{context_block}
Below are detailed notes extracted segment-by-segment from the FULL transcript.
The timestamps in the notes are taken directly from the original recording.

{all_notes}

Using these notes, produce a complete structured analysis covering the ENTIRE conversation:

## Overview
2–3 sentences describing what this conversation is about and its general tone.

## Participants
One line per person: their name, role or background (if evident), and their general stance in this discussion.

## Key Takeaways
List 10–20 of the most important points, arguments, or insights from the full conversation.
Draw from all segments — do not favour the beginning over the end.
For each takeaway:
- State it clearly in 2–4 sentences.
- Note who made the point.
- Include the original timestamp [HH:MM:SS].

Format each as:
**N. [HH:MM:SS] — Short title of the point**
Body text here. (Speaker Name)

## Main Themes
List 3–6 overarching themes with the time ranges from the original transcript.
Format: **Theme name** [HH:MM:SS – HH:MM:SS]: Brief description.

## Notable Agreements & Disagreements
Highlight 2–5 moments where speakers meaningfully agreed or disagreed.
Include the original timestamp and a one-sentence description.

Use clean markdown formatting throughout."""

    return _chat(prompt, max_tokens=6000)

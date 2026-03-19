# transcript-v2

Transcribe, analyze, and summarize long-form audio and video — from local files or any YouTube / podcast URL.

Built for panel discussions, interviews, and conversations between 2–4 people lasting anywhere from 30 minutes to 5+ hours. The program identifies who is speaking, cleans up the dialogue so it is easy to follow, and produces a structured summary with key takeaways linked to exact timestamps in the original recording.

---

## What it produces

For every recording you run, four files are saved to the `output/` folder:

| File | Contents |
|---|---|
| `<title>_transcript.md` | Full timestamped dialogue in Markdown |
| `<title>_transcript.txt` | Full timestamped dialogue in plain text |
| `<title>_summary.md` | Structured analysis in Markdown |
| `<title>_summary.txt` | Structured analysis in plain text |

The summary includes:
- **Overview** — what the conversation is about and its tone
- **Participants** — who is speaking and their role
- **Key Takeaways** — 10–20 insights, each with the timestamp where it was discussed
- **Main Themes** — overarching topics with time ranges
- **Notable Agreements & Disagreements** — moments of alignment or tension between speakers

---

## Requirements

- Python 3.10 or later
- [ffmpeg](https://ffmpeg.org/download.html) — required for audio extraction from video files
- API keys for:
  - [AssemblyAI](https://www.assemblyai.com/) — transcription and speaker identification (free tier available)
  - [Anthropic Claude](https://platform.claude.com/settings/api-keys) **or** [OpenAI](https://platform.openai.com/api-keys) — analysis and summarization

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/kpashoks/transcript-v2.git
cd transcript-v2
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install ffmpeg

**Windows** — download from https://ffmpeg.org/download.html and add `ffmpeg/bin` to your system PATH, or install via [Chocolatey](https://chocolatey.org/):
```bash
choco install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt install ffmpeg
```

### 4. Configure your API keys

Copy the example environment file and fill in your keys:

```bash
cp .env.example .env
```

Open `.env` in a text editor:

```
ASSEMBLYAI_API_KEY=your_assemblyai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here

# AI provider for analysis — "anthropic" (Claude) or "openai" (GPT-4o)
AI_PROVIDER=anthropic
```

You only need **one** of the AI analysis keys (Anthropic or OpenAI). Set `AI_PROVIDER` to match the key you provide.

**Where to get each key:**
- AssemblyAI → https://www.assemblyai.com/ (free tier: 100 hours/month)
- Anthropic Claude → https://platform.claude.com/settings/api-keys (requires adding billing credits)
- OpenAI → https://platform.openai.com/api-keys (requires adding billing credits)

---

## Usage

### Analyze a YouTube video

```bash
python main.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

### Analyze a local file

```bash
python main.py /path/to/recording.mp3
python main.py /path/to/interview.mkv
python main.py /path/to/podcast.m4a
```

### Improve accuracy with optional hints

#### `--speakers N` — tell the program how many speakers to expect

```bash
python main.py "https://..." --speakers 2
```

Helps AssemblyAI's speaker detection for recordings where voices are similar or overlap.

#### `--context "..."` — describe who is speaking and what the conversation is about

```bash
python main.py "https://..." --context "This is the Dwarkesh Podcast. Dwarkesh Patel is the host. Dylan Patel is the guest, founder of SemiAnalysis, discussing AI compute bottlenecks."
```

The context is used to:
- Correctly identify speaker names even if they are never introduced on-screen
- Improve the relevance and accuracy of the summary

#### `--output-dir /path/to/folder` — save files to a specific directory

```bash
python main.py "https://..." --output-dir ~/Desktop/summaries
```

### Full example

```bash
python main.py "https://www.youtube.com/watch?v=mDG_Hx3BSUE" \
  --speakers 2 \
  --context "Dwarkesh Podcast. Dwarkesh Patel is the host. Dylan Patel (SemiAnalysis) is the guest, discussing AI compute bottlenecks: logic, memory, and power." \
  --output-dir ./output
```

---

## Supported sources

The program uses [yt-dlp](https://github.com/yt-dlp/yt-dlp) for downloading, which supports **1,000+ sites** including:

- YouTube
- Vimeo
- Twitter / X
- Spotify (public episodes)
- SoundCloud
- Direct MP3/MP4 URLs
- Local files (MP3, MP4, MKV, M4A, WAV, and more)

---

## How it works

```
 Input (URL or local file)
         │
         ▼
 ┌───────────────┐
 │  downloader   │  yt-dlp extracts audio to MP3 (URLs only)
 └───────┬───────┘
         │
         ▼
 ┌───────────────┐
 │  transcriber  │  AssemblyAI transcribes audio with speaker diarization
 └───────┬───────┘  Returns timestamped utterances labeled Speaker A, B, C…
         │
         ▼
 ┌───────────────┐
 │   analyzer    │  Claude / GPT-4o identifies real speaker names from context
 │               │  then summarizes the full transcript
 │               │  → short transcripts: single-pass analysis
 │               │  → long transcripts:  map→merge (chunk → summarize → merge)
 └───────┬───────┘
         │
         ▼
 ┌───────────────┐
 │   formatter   │  Renders transcript and summary as .md and .txt files
 └───────┬───────┘
         │
         ▼
 output/<title>_transcript.md / .txt
 output/<title>_summary.md    / .txt
```

### Component overview

| File | Role |
|---|---|
| `main.py` | Entry point. Parses arguments, orchestrates the four steps, saves output. |
| `downloader.py` | Downloads audio from any URL via yt-dlp and converts to MP3. |
| `transcriber.py` | Sends audio to AssemblyAI and returns timestamped, speaker-labeled utterances. |
| `analyzer.py` | Identifies speaker names and generates the structured summary using Claude or GPT-4o. Handles long transcripts via map→merge chunking. |
| `formatter.py` | Converts raw utterances and AI-generated Markdown into clean `.md` and `.txt` output files. |
| `config.py` | Loads API keys and settings from `.env`. |

### Handling long recordings

For recordings longer than roughly 90 minutes, the transcript exceeds what fits in a single AI context window. The analyzer automatically splits it into overlapping chunks, summarizes each chunk individually (the **map** step), then synthesizes all the chunk summaries into a single coherent document (the **merge** step). Timestamps in the final output always refer to the original recording.

---

## Cost estimates

| Recording length | AssemblyAI | Claude (Sonnet) | OpenAI (GPT-4o) |
|---|---|---|---|
| 30 min | ~$0.15 | ~$0.05 | ~$0.10 |
| 60 min | ~$0.30 | ~$0.10 | ~$0.20 |
| 2 hours | ~$0.60 | ~$0.20 | ~$0.40 |
| 5 hours | ~$1.50 | ~$0.50 | ~$1.00 |

AssemblyAI pricing: $0.0035/min for Universal-2 model.
Claude / GPT-4o costs are estimates based on typical transcript lengths.

---

## Troubleshooting

**`ERROR: unable to download video data: HTTP Error 403`**
Your yt-dlp version may be outdated. Run:
```bash
pip install -U yt-dlp
```

**`Your credit balance is too low`** (Anthropic)
Credits can take up to 30 minutes to activate after purchase. Check your balance at https://platform.claude.com/settings/billing. If Anthropic is not working yet, switch to OpenAI by setting `AI_PROVIDER=openai` in `.env`.

**Speaker names shown as "Speaker A", "Speaker B"**
Add a `--context` description telling the program who the speakers are. See the [Usage](#usage) section above.

**`ffmpeg not found`**
ffmpeg must be installed and available on your system PATH. See [Setup step 3](#3-install-ffmpeg).

---

## License

MIT — free to use, modify, and distribute.

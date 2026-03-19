"""
transcript-v2 Web UI — Flask application.

Start with:
    python app.py

Then open http://localhost:5000 in your browser.

The server streams real-time progress back to the browser using
Server-Sent Events (SSE) so you can watch each step complete live.
"""

import json
import os
import queue
import shutil
import tempfile
import threading
import uuid
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2 GB max upload

# In-memory job registry { job_id: {"status", "result", "error"} }
_jobs: dict[str, dict] = {}
# Per-job SSE queues { job_id: queue.Queue }
_queues: dict[str, queue.Queue] = {}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    """Start an analysis job. Returns {"job_id": "..."}."""
    job_id = str(uuid.uuid4())
    _queues[job_id] = queue.Queue()
    _jobs[job_id] = {"status": "running", "result": None, "error": None}

    # Collect form fields
    url = request.form.get("url", "").strip()
    context = request.form.get("context", "").strip() or None
    speakers_raw = request.form.get("speakers", "").strip()
    num_speakers = int(speakers_raw) if speakers_raw.isdigit() else None
    no_cache = request.form.get("no_cache") == "1"

    # Handle optional file upload
    uploaded_file = request.files.get("file")
    tmp_upload_path: Path | None = None
    source: str = url

    if uploaded_file and uploaded_file.filename:
        suffix = Path(uploaded_file.filename).suffix or ".mp3"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix,
                                          prefix="transcript_upload_")
        uploaded_file.save(tmp.name)
        tmp.close()
        tmp_upload_path = Path(tmp.name)
        source = str(tmp_upload_path)

    if not source:
        return jsonify({"error": "Provide a URL or upload a file."}), 400

    thread = threading.Thread(
        target=_run_analysis,
        args=(job_id, source, context, num_speakers, no_cache, tmp_upload_path),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/progress/<job_id>")
def progress(job_id: str):
    """SSE endpoint — streams progress events until the job finishes."""
    def generate():
        q = _queues.get(job_id)
        if q is None:
            yield _sse({"type": "error", "message": "Job not found."})
            return
        while True:
            try:
                event = q.get(timeout=30)
            except queue.Empty:
                yield _sse({"type": "ping"})   # keep-alive
                continue
            yield _sse(event)
            if event.get("type") in ("done", "error"):
                break

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/download/<path:filename>")
def download(filename: str):
    """Serve a file from the output directory."""
    from config import OUTPUT_DIR
    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        return "File not found.", 404
    return send_file(file_path, as_attachment=True)


# ---------------------------------------------------------------------------
# Background job runner
# ---------------------------------------------------------------------------

def _run_analysis(
    job_id: str,
    source: str,
    context: str | None,
    num_speakers: int | None,
    no_cache: bool,
    tmp_upload_path: Path | None,
) -> None:
    q = _queues[job_id]

    def emit(msg: str):
        q.put({"type": "progress", "message": msg})

    try:
        from config import OUTPUT_DIR
        import cache as cache_mod
        from analyzer import identify_speakers, summarize
        from formatter import format_transcript, save_outputs

        is_url = source.startswith("http://") or source.startswith("https://")

        # ---- Step 1: acquire audio ----------------------------------------
        if is_url:
            emit("Downloading audio from URL…")
            from downloader import download_audio
            tmp_dir = Path(tempfile.mkdtemp(prefix="transcript_v2_"))
            try:
                audio_path, title = download_audio(source, tmp_dir)
                emit(f"Downloaded: {title}")
                utterances, speaker_names, summary_text = _process_audio(
                    audio_path=audio_path,
                    title=title,
                    num_speakers=num_speakers,
                    context=context,
                    no_cache=no_cache,
                    cache_source=source,
                    emit=emit,
                )
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)
        else:
            audio_path = Path(source)
            title = audio_path.stem
            emit(f"Using uploaded file: {audio_path.name}")
            utterances, speaker_names, summary_text = _process_audio(
                audio_path=audio_path,
                title=title,
                num_speakers=num_speakers,
                context=context,
                no_cache=no_cache,
                cache_source=None,
                emit=emit,
            )

        # ---- Step 4: save output ------------------------------------------
        emit("Saving output files…")
        transcript_text = format_transcript(utterances, speaker_names)
        paths = save_outputs(title, transcript_text, summary_text, OUTPUT_DIR)

        result = {
            "title": title,
            "speakers": speaker_names,
            "summary_md": summary_text,
            "files": [p.name for p in paths],
        }

        _jobs[job_id] = {"status": "done", "result": result, "error": None}
        q.put({"type": "done", "result": result})

    except Exception as exc:
        import traceback
        detail = traceback.format_exc()
        _jobs[job_id] = {"status": "error", "result": None, "error": str(exc)}
        q.put({"type": "error", "message": str(exc), "detail": detail})

    finally:
        # Clean up the temporary uploaded file if there was one
        if tmp_upload_path and tmp_upload_path.exists():
            tmp_upload_path.unlink(missing_ok=True)


def _process_audio(
    audio_path: Path,
    title: str,
    num_speakers: int | None,
    context: str | None,
    no_cache: bool,
    cache_source: str | None,
    emit,
) -> tuple[list[dict], dict[str, str], str]:
    """Transcribe → identify speakers → summarize."""
    import cache as cache_mod
    from analyzer import identify_speakers, summarize

    # ---- Step 2: transcribe (or load cache) -------------------------------
    key = (
        cache_mod.cache_key_for_url(cache_source)
        if cache_source
        else cache_mod.cache_key_for_file(audio_path)
    )

    cached = cache_mod.load(key) if not no_cache else None

    if cached:
        utterances = cached["utterances"]
        emit(f"Loaded from cache — {len(utterances):,} utterances. Skipped AssemblyAI upload.")
    else:
        emit("Uploading to AssemblyAI for transcription (this may take several minutes)…")
        from transcriber import transcribe
        utterances = transcribe(audio_path, num_speakers=num_speakers)
        n_spk = len(set(u["speaker"] for u in utterances))
        emit(f"Transcription complete — {len(utterances):,} utterances, {n_spk} speakers detected.")
        cache_mod.save(key, utterances, title)
        emit("Transcript saved to cache.")

    # ---- Step 3: analyze --------------------------------------------------
    emit("Identifying speakers…")
    speaker_names = identify_speakers(utterances, context=context)
    names_str = ", ".join(f"{k}={v}" for k, v in speaker_names.items())
    emit(f"Speakers identified: {names_str}")

    emit("Generating summary and analysis (this may take a minute)…")
    summary_text = summarize(utterances, speaker_names, title, context=context)
    emit("Analysis complete.")

    return utterances, speaker_names, summary_text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  transcript-v2 UI  ->  http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)

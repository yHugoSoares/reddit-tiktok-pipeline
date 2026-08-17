#!/usr/bin/env python3
"""Reddit Story Video Studio — local web app.

Inputs: Reddit post URL + YouTube background URL.
Pipeline: fetch post (public JSON, no API creds) → TTS → subtitles
→ chop background → compose final video. Results served for download.
"""

import glob
import io
import json
import logging
import math
import os
import re
import shutil
import sys
import threading
import traceback
import uuid
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory, abort

load_dotenv()

app = Flask(__name__)

JOBS = {}
JOBS_LOCK = threading.Lock()

logger = logging.getLogger("studio")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

RESULT_DIR = Path("results")
BG_VIDEO_DIR = Path("assets/backgrounds/video")


# ---------------------------------------------------------------------------
# Job helpers
# ---------------------------------------------------------------------------

def new_job():
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {
        "status": "queued",
        "logs": [],
        "video": None,
        "error": None,
        "created": datetime.now().isoformat(),
        "finished": None,
    }
    return job_id


def log(job_id, message):
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id]["logs"].append(f"{datetime.now().strftime('%H:%M:%S')} {message}")


class TeeStream(io.TextIOBase):
    """Redirect stdout/stderr into a job's log list as well as the real stream."""

    def __init__(self, job_id, real_stream):
        self.job_id = job_id
        self.real = real_stream

    def write(self, s):
        line = s.strip()
        if line:
            log(self.job_id, line)
        return len(s)

    def flush(self):
        try:
            self.real.flush()
        except Exception:
            pass


class LogHandler(logging.Handler):
    def __init__(self, job_id):
        super().__init__()
        self.job_id = job_id

    def emit(self, record):
        log(self.job_id, record.getMessage())


# ---------------------------------------------------------------------------
# Reddit fetch (public JSON — no API credentials needed)
# ---------------------------------------------------------------------------

def extract_reddit_id(url: str) -> str:
    m = re.search(r"comments/([a-z0-9]+)", url, re.IGNORECASE)
    if not m:
        raise ValueError("Could not find a post ID in that Reddit URL.")
    return m.group(1)


def fetch_reddit_post(url: str) -> dict:
    """Fetch a Reddit post via praw (OAuth). Requires real creds in .env."""
    import praw

    reddit = praw.Reddit(
        client_id=os.environ.get("REDDIT_CLIENT_ID", ""),
        client_secret=os.environ.get("REDDIT_CLIENT_SECRET", ""),
        username=os.environ.get("REDDIT_USERNAME", ""),
        password=os.environ.get("REDDIT_PASSWORD", ""),
        user_agent="reddit-story-video-studio/1.0",
    )
    submission = reddit.submission(url=url)
    title = (submission.title or "").strip()
    selftext = (submission.selftext or "") or ""
    subreddit = str(submission.subreddit)
    return {
        "id": submission.id,
        "title": title,
        "body": selftext,
        "subreddit": subreddit,
        "url": f"https://www.reddit.com{submission.permalink}",
    }


# ---------------------------------------------------------------------------
# Background download (YouTube URL → local file, cached by video ID)
# ---------------------------------------------------------------------------

def download_youtube_background(url: str) -> str:
    """Download the background video, return its filename (e.g. 'abc123.mp4')."""
    import yt_dlp

    BG_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        "format": "bestvideo[height<=1080][ext=mp4]/best[height<=1080][ext=mp4]/best[height<=1080]",
        "outtmpl": str(BG_VIDEO_DIR / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "retries": 5,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_id = info.get("id")
        ext = info.get("ext", "mp4")
    return f"{video_id}.{ext}"


# ---------------------------------------------------------------------------
# Pipeline (mirrors test_pipeline.py but with real inputs)
# ---------------------------------------------------------------------------

def run_pipeline(job_id, reddit_url, youtube_url, story_title="", story_body=""):
    try:
        # 1. config
        from init_config import generate as init_config
        init_config()
        import toml as _toml
        from utils import settings
        settings.config = _toml.load("config.toml")
        settings.config["settings"]["storymode"] = True
        settings.config["settings"]["storymodemethod"] = 1
        if settings.config["settings"].get("storymode_max_length", 1000) < 5000:
            settings.config["settings"]["storymode_max_length"] = 5000

        # 2. fetch reddit post (or use pasted story)
        if story_body.strip():
            import hashlib as _hl
            post = {
                "id": _hl.md5((story_title + story_body).encode()).hexdigest()[:8],
                "title": story_title.strip(),
                "body": story_body,
                "subreddit": os.environ.get("REDDIT_SUBREDDIT", "AmItheAsshole"),
                "url": "",
            }
            log(job_id, "Using pasted story text.")
        else:
            log(job_id, "Fetching Reddit post...")
            post = fetch_reddit_post(reddit_url)
        log(job_id, f"r/{post['subreddit']}: {post['title'][:70]}")
        settings.config["reddit"]["thread"]["subreddit"] = post["subreddit"]

        # 3. split sentences
        import re as _re
        from utils.posttextparser import posttextparser
        text = _re.sub(r"\[deleted\]|\[removed\]|\(?https?://\S+\)?", "", post["body"])
        text = _re.sub(r"&amp;", "&", text)
        text = _re.sub(r"\s+", " ", text).strip()
        if not text:
            raise ValueError("That post has no text content (maybe a link/image post).")

        all_sentences = posttextparser(text)
        if not all_sentences:
            raise ValueError("Could not split the post into sentences.")

        hook = all_sentences[0]
        body_sentences = all_sentences[1:] if len(all_sentences) > 1 else all_sentences[:]
        if not body_sentences:
            body_sentences = [hook]

        reddit_id = post["id"]
        reddit_object = {
            "thread_id": reddit_id,
            "thread_url": post["url"],
            "thread_title": hook,
            "thread_post": body_sentences,
            "comments": [],
            "post_url": post["url"],
        }
        log(job_id, f"{len(all_sentences)} sentences, {len(text)} chars")

        # 4. TTS
        log(job_id, "Generating TTS (Edge TTS)...")
        from video_creation.voices import save_text_to_mp3
        length, number_of_clips = save_text_to_mp3(reddit_object)
        length = max(math.ceil(length), 1)
        log(job_id, f"TTS done: {length}s, {number_of_clips} segments")

        # 5. subtitles
        log(job_id, "Generating subtitle overlays...")
        from subtitle_generator import generate_subtitle_overlays
        temp_png = f"assets/temp/{reddit_id}/png"
        if os.path.exists(temp_png):
            shutil.rmtree(temp_png)
        generate_subtitle_overlays(reddit_id, body_sentences, temp_png)
        log(job_id, f"{len(body_sentences)} subtitle overlays")

        from karaoke_generator import generate_karaoke_for_reddit
        n_karaoke = generate_karaoke_for_reddit(reddit_id, body_sentences)
        if n_karaoke:
            log(job_id, f"Reactive subtitles: {n_karaoke} sentence clips")

        # 6. background
        from video_creation.background import (
            chop_background, download_background_audio,
            download_background_video, get_background_config, register_local_backgrounds,
        )

        if youtube_url:
            log(job_id, f"Downloading background from YouTube...")
            fname = download_youtube_background(youtube_url)
            register_local_backgrounds()  # re-scan so the new file is in the registry
            settings.config["settings"]["background"]["background_video"] = Path(fname).stem
            log(job_id, f"Background: {fname}")
        else:
            log(job_id, "Using existing local background...")
            register_local_backgrounds()

        bg_config = {"video": get_background_config("video"), "audio": get_background_config("audio")}
        try:
            download_background_video(bg_config["video"])
        except Exception as e:
            log(job_id, f"Background dl note: {e}")
        try:
            download_background_audio(bg_config["audio"])
        except Exception as e:
            log(job_id, f"Audio dl note: {e}")
        chop_background(bg_config, length, reddit_object)

        # 7. compose
        log(job_id, "Rendering final video... (this takes a few minutes)")
        from video_creation.final_video import make_final_video
        os.makedirs("results", exist_ok=True)
        make_final_video(number_of_clips, length, reddit_object, bg_config)

        # 8. locate output
        result_files = glob.glob("results/**/*.mp4", recursive=True)
        if not result_files:
            raise RuntimeError("No MP4 was produced.")
        latest = max(result_files, key=os.path.getmtime)
        size = os.path.getsize(latest)
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "done"
            JOBS[job_id]["video"] = latest
            JOBS[job_id]["finished"] = datetime.now().isoformat()
        log(job_id, f"DONE — {latest} ({size // (1024 * 1024)} MB)")

        from utils.cleanup import cleanup
        try:
            cleanup(reddit_id)
        except Exception:
            pass

    except Exception as e:
        logger.exception("Job %s failed", job_id)
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "error"
            JOBS[job_id]["error"] = f"{type(e).__name__}: {e}"
            JOBS[job_id]["finished"] = datetime.now().isoformat()
        log(job_id, f"ERROR: {type(e).__name__}: {e}")


def start_job(reddit_url, youtube_url, story_title="", story_body=""):
    job_id = new_job()
    with JOBS_LOCK:
        JOBS[job_id]["status"] = "running"

    handler = LogHandler(job_id)
    logging.getLogger().addHandler(handler)
    tee_out = TeeStream(job_id, sys.__stdout__)
    tee_err = TeeStream(job_id, sys.__stderr__)

    def worker():
        with redirect_stdout(tee_out), redirect_stderr(tee_err):
            try:
                run_pipeline(job_id, reddit_url, youtube_url, story_title, story_body)
            finally:
                logging.getLogger().removeHandler(handler)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return job_id


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.get_json(silent=True) or request.form
    reddit_url = (data.get("reddit_url") or "").strip()
    youtube_url = (data.get("youtube_url") or "").strip()
    story_title = (data.get("story_title") or "").strip()
    story_body = (data.get("story_body") or "").strip()
    if not reddit_url and not story_body:
        return jsonify({"error": "Provide a Reddit URL or paste story text."}), 400
    job_id = start_job(reddit_url, youtube_url, story_title, story_body)
    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>")
def api_status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Unknown job"}), 404
    return jsonify({
        "status": job["status"],
        "logs": job["logs"],
        "video": job["video"],
        "error": job["error"],
    })


@app.route("/api/videos")
def api_videos():
    files = sorted(glob.glob("results/**/*.mp4", recursive=True), key=os.path.getmtime, reverse=True)
    return jsonify([{"path": f, "name": os.path.basename(f), "size": os.path.getsize(f)} for f in files])


@app.route("/results/<path:filename>")
def results_file(filename):
    return send_from_directory(str(RESULT_DIR), filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5070"))
    host = os.environ.get("HOST", "0.0.0.0")
    app.run(host=host, port=port, debug=False, threaded=True)
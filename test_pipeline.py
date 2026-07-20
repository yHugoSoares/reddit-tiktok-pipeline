#!/usr/bin/env python3
"""Dry-run the full pipeline with a mock Reddit story — no API creds needed.

Tests: TTS → subtitle overlays → background → video render → platform upload
When Reddit API is approved, just fill in .env creds and swap this out.
"""

import glob
import json
import logging
import math
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Logging ──
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ── Mock Reddit story ──
STORY_TITLE = "AITA for telling my roommate her boyfriend can't live with us rent-free?"
STORY_BODY = (
    "My roommate Sarah and I have been living together for two years. Everything was fine "
    "until three months ago when she started dating Jake. At first he was over maybe twice "
    "a week, which was totally fine. But then it became four nights. Then five. Then suddenly "
    "he had a key and his toothbrush was in our bathroom and his PS5 was in our living room. "
    "I asked Sarah about it and she said he was going through a rough patch and just needed "
    "a place to crash for a few weeks. That was two months ago. He doesn't pay rent. He doesn't "
    "buy groceries. He leaves dishes everywhere. He uses my shampoo. Last week I came home and "
    "he was in my room playing my Nintendo Switch without asking. I told Sarah that either he "
    "starts paying a third of everything or he needs to leave. She called me heartless and said "
    "I was being a terrible friend. Now half our friend group thinks I'm an awful person. "
    "Am I really the one in the wrong here?"
)

DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"

# ── Helpers ──
def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def atomic_write_json(path, data):
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)

# ── Main ──
def main():
    # Init config — generate from .env, load directly (skip interactive prompts)
    from init_config import generate
    generate()

    import toml as _toml
    from utils import settings
    settings.config = _toml.load("config.toml")

    settings.config["settings"]["storymode"] = True
    settings.config["settings"]["storymodemethod"] = 1
    if settings.config["settings"].get("storymode_max_length", 1000) < 5000:
        settings.config["settings"]["storymode_max_length"] = 5000

    # Build mock reddit_object
    import hashlib, re
    from utils.posttextparser import posttextparser

    text = re.sub(r'\[deleted\]|\[removed\]|\(?https?://\S+\)?', '', STORY_BODY)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'\s+', ' ', text).strip()

    all_sentences = posttextparser(text)
    if not all_sentences:
        logger.error("No sentences extracted.")
        sys.exit(1)

    hook = all_sentences[0]
    body_sentences = all_sentences[1:] if len(all_sentences) > 1 else all_sentences[:]
    if not body_sentences:
        body_sentences = [hook]

    reddit_id = hashlib.md5(STORY_TITLE.encode()).hexdigest()[:8]
    subreddit = os.environ.get("REDDIT_SUBREDDIT", "AmItheAsshole")

    reddit_object = {
        "thread_id": reddit_id,
        "thread_url": f"https://reddit.com/r/{subreddit}/comments/{reddit_id}",
        "thread_title": hook,
        "thread_post": body_sentences,
        "comments": [],
        "post_url": f"https://reddit.com/r/{subreddit}/comments/{reddit_id}",
    }

    logger.info("Using mock story: '%s...' (%d chars, %d sentences)",
                 hook[:60], len(text), len(all_sentences))

    # Dedup check
    STATE_DIR = Path("state")
    STATE_DIR.mkdir(exist_ok=True)
    POSTED_IDS_FILE = STATE_DIR / "posted_ids.json"
    posted = load_json(POSTED_IDS_FILE, {"posted_story_ids": []})
    if reddit_id in posted.get("posted_story_ids", []):
        logger.info("Story already processed. Skipping.")
        sys.exit(0)

    # TTS
    logger.info("Generating TTS...")
    from video_creation.voices import save_text_to_mp3
    length, number_of_clips = save_text_to_mp3(reddit_object)
    length = max(math.ceil(length), 1)
    logger.info("TTS: %ds, %d segments", length, number_of_clips)

    # Subtitle overlays
    logger.info("Generating subtitles...")
    from subtitle_generator import generate_subtitle_overlays
    temp_png = f"assets/temp/{reddit_id}/png"
    if os.path.exists(temp_png):
        shutil.rmtree(temp_png)
    generate_subtitle_overlays(reddit_id, body_sentences, temp_png)
    logger.info("Subtitles: %d overlays", len(body_sentences))

    # Background
    logger.info("Preparing background...")
    from video_creation.background import (
        chop_background, download_background_audio,
        download_background_video, get_background_config,
    )
    from video_creation.background import register_local_backgrounds
    register_local_backgrounds()

    bg_config = {"video": get_background_config("video"), "audio": get_background_config("audio")}
    try:
        download_background_video(bg_config["video"])
    except Exception as e:
        logger.warning("Background dl: %s", e)
    try:
        download_background_audio(bg_config["audio"])
    except Exception as e:
        logger.warning("Audio dl: %s", e)
    chop_background(bg_config, length, reddit_object)

    # Compose video
    logger.info("Rendering final video...")
    from video_creation.final_video import make_final_video
    os.makedirs("results", exist_ok=True)
    make_final_video(number_of_clips, length, reddit_object, bg_config)

    # Locate output
    result_files = glob.glob("results/**/*.mp4", recursive=True)
    if not result_files:
        logger.error("No MP4 output!")
        sys.exit(1)

    latest = max(result_files, key=os.path.getmtime)
    size = os.path.getsize(latest)
    logger.info("Video: %s (%d bytes)", latest, size)

    if size == 0:
        logger.error("Empty video!")
        sys.exit(1)

    # Caption
    import hashlib as hl
    captions = [
        "I would have left immediately 😳 #reddit #storytime #fyp",
        "This got worse with every sentence… #reddit #storytime #fyp",
    ]
    caption = captions[int(hl.md5(reddit_id.encode()).hexdigest(), 16) % len(captions)]

    youtube_title = f"Reddit Story: {hook[:90]}"

    logger.info("=" * 50)
    logger.info("VIDEO GENERATED SUCCESSFULLY ✓")
    logger.info("  File:      %s", latest)
    logger.info("  Size:      %d MB", size // (1024 * 1024))
    logger.info("  Duration:  %ds", length)
    logger.info("  TikTok:    %s", caption)
    logger.info("  YouTube:   %s", youtube_title)
    logger.info("=" * 50)

    # Platform uploads
    PLATFORMS = os.environ.get("PLATFORMS", "").lower().split(",")
    PLATFORMS = [p.strip() for p in PLATFORMS if p.strip()]
    if DRY_RUN:
        PLATFORMS = []

    video_abs = os.path.abspath(latest)
    insta_cap = f"{caption}\n\n#reddit #storytime #aita"

    uploaded = {}

    if "tiktok" in PLATFORMS:
        from upload_tiktok import upload_video
        acct = os.environ.get("TIKTOK_ACCOUNTNAME", "")
        if acct:
            uploaded["tiktok"] = upload_video(video_abs, caption, acct)

    if "instagram" in PLATFORMS:
        from upload_instagram import upload_to_instagram
        u = os.environ.get("INSTAGRAM_USERNAME", "")
        p = os.environ.get("INSTAGRAM_PASSWORD", "")
        if u and p:
            uploaded["instagram"] = upload_to_instagram(video_abs, insta_cap, u, p)

    if "youtube" in PLATFORMS:
        from upload_youtube import upload_to_youtube
        uploaded["youtube"] = upload_to_youtube(video_abs, youtube_title, youtube_title)

    logger.info("Uploads: %s", json.dumps(uploaded) if uploaded else "(dry-run)")

    # Cleanup
    from utils.cleanup import cleanup
    cleanup(reddit_id)
    logger.info("Done!")


if __name__ == "__main__":
    main()

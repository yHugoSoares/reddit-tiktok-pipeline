#!/usr/bin/env python3
"""
Automated Reddit-Story TikTok Pipeline.

Orchestrates: Reddit fetch → TTS → subtitle overlay generation
→ video composition → TikTok upload (or dry-run log).

Entry point for Docker container. Scheduled by host cron or Ofelia.
"""

import glob
import hashlib
import json
import logging
import math
import os
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
log_filename = f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / log_filename),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"
POSTS_PER_DAY = int(os.environ.get("POSTS_PER_DAY", "1"))
TIKTOK_ACCOUNTNAME = os.environ.get("TIKTOK_ACCOUNTNAME", "").strip()
INSTAGRAM_USERNAME = os.environ.get("INSTAGRAM_USERNAME", "").strip()
INSTAGRAM_PASSWORD = os.environ.get("INSTAGRAM_PASSWORD", "").strip()

# Platforms enabled for upload
PLATFORMS = os.environ.get("PLATFORMS", "tiktok,instagram,youtube").lower().split(",")
PLATFORMS = [p.strip() for p in PLATFORMS if p.strip()]
if DRY_RUN:
    PLATFORMS = []

logger.info(
    "Starting pipeline | DRY_RUN=%s | POSTS_PER_DAY=%s | PLATFORMS=%s",
    DRY_RUN, POSTS_PER_DAY, ", ".join(PLATFORMS) or "none (dry-run)",
)

# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

STATE_DIR = Path("state")
STATE_DIR.mkdir(exist_ok=True)
POSTED_IDS_FILE = STATE_DIR / "posted_ids.json"
UPLOAD_HISTORY_FILE = STATE_DIR / "upload_history.json"


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


def check_daily_limit():
    """Exit if today's upload count exceeds POSTS_PER_DAY."""
    history = load_json(UPLOAD_HISTORY_FILE, {"videos": []})
    today = datetime.now().strftime("%Y-%m-%d")
    today_count = sum(1 for v in history["videos"] if v["uploaded_at"].startswith(today))
    if today_count >= POSTS_PER_DAY:
        logger.info("Daily limit reached: %d/%d. Exiting.", today_count, POSTS_PER_DAY)
        sys.exit(0)
    return history


def is_already_posted(story_id):
    posted = load_json(POSTED_IDS_FILE, {"posted_story_ids": []})
    return story_id in posted.get("posted_story_ids", [])


def mark_posted(story_id, subreddit, caption, background_name, filename):
    posted = load_json(POSTED_IDS_FILE, {"posted_story_ids": []})
    if story_id not in posted["posted_story_ids"]:
        posted["posted_story_ids"].append(story_id)
    atomic_write_json(POSTED_IDS_FILE, posted)

    history = load_json(UPLOAD_HISTORY_FILE, {"videos": []})
    history["videos"].append({
        "story_id": story_id,
        "source_subreddit": subreddit,
        "file": filename,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "caption": caption,
        "background": background_name,
    })
    atomic_write_json(UPLOAD_HISTORY_FILE, history)
    logger.info("Story %s marked as posted.", story_id)


# ---------------------------------------------------------------------------
# Caption templates
# ---------------------------------------------------------------------------

CAPTION_TEMPLATES = [
    "I would have left immediately 😳 #reddit #storytime #fyp",
    "This got worse with every sentence… #reddit #storytime #fyp",
    "Would you forgive them after this? #reddit #storytime #fyp",
    "The audacity is unreal 💀 #reddit #storytime #fyp",
    "Plot twist of the century 🔥 #reddit #storytime #fyp",
    "I can't believe what I just read 😱 #reddit #storytime #fyp",
    "This is why I don't talk to people #reddit #storytime #fyp",
    "The way this escalated though… #reddit #storytime #fyp",
]


def select_caption(story_id):
    """Deterministic caption selection based on story ID hash."""
    idx = int(hashlib.md5(story_id.encode()).hexdigest(), 16) % len(CAPTION_TEMPLATES)
    return CAPTION_TEMPLATES[idx]


# ---------------------------------------------------------------------------
# Background selection
# ---------------------------------------------------------------------------

def select_background(reddit_id, video_length):
    """Select a background video. Prefers local MP4s over YouTube downloads.

    Returns (background_name, has_local) tuple.
    """
    bg_dir = Path("assets/backgrounds")
    local_mp4s = list(bg_dir.glob("*.mp4"))

    if local_mp4s:
        # Deterministic round-robin based on day
        day_seed = datetime.now().strftime("%Y%m%d")
        idx = int(hashlib.md5(day_seed.encode()).hexdigest(), 16) % len(local_mp4s)
        chosen = local_mp4s[idx]

        # Ensure video/ subdir exists for upstream compatibility
        video_dir = bg_dir / "video"
        video_dir.mkdir(exist_ok=True)

        # Copy to the expected upstream path format
        dest = video_dir / f"local-{chosen.name}"
        if not dest.exists():
            shutil.copy2(chosen, dest)

        logger.info("Using local background: %s", chosen.name)
        return f"local-{chosen.name}", True

    return None, False


def discover_local_backgrounds():
    """Add local MP4 files to the upstream background registry."""
    bg_dir = Path("assets/backgrounds")
    local_mp4s = list(bg_dir.glob("*.mp4"))

    if not local_mp4s:
        return

    video_dir = bg_dir / "video"
    video_dir.mkdir(exist_ok=True)

    for mp4 in local_mp4s:
        dest = video_dir / f"local-{mp4.name}"
        if not dest.exists():
            shutil.copy2(mp4, dest)

    logger.info("Discovered %d local background(s).", len(local_mp4s))


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main():
    # ---- 0. Auto-generate config if missing ----
    from init_config import generate as init_config
    init_config()

    # ---- 1. Daily limit check ----
    check_daily_limit()

    # ---- 2. Initialize upstream config ----
    from utils import settings

    config_dir = Path.cwd()
    config = settings.check_toml(
        str(config_dir / "utils" / ".config.template.toml"),
        str(config_dir / "config.toml"),
    )
    if config is False:
        logger.error("Config validation failed. Run interactive setup first: touch config.toml && docker compose run --rm -v \"$(pwd)/config.toml:/app/video_bot/config.toml\" reddit-bot python main.py")
        sys.exit(1)

    # Force story mode (we always narrate post selftext, not comments)
    settings.config["settings"]["storymode"] = True
    settings.config["settings"]["storymodemethod"] = 1

    # Storymode max length: allow up to 5000 chars for longer stories
    if settings.config["settings"].get("storymode_max_length", 1000) < 5000:
        settings.config["settings"]["storymode_max_length"] = 5000

    # ---- 3. Fetch Reddit story ----
    logger.info("Fetching Reddit story from r/%s ...", settings.config["reddit"]["thread"]["subreddit"])
    from reddit.subreddit import get_subreddit_threads
    from utils.id import extract_id

    reddit_object = get_subreddit_threads(POST_ID=None)
    if reddit_object is None:
        logger.error("No Reddit thread returned. Check subreddit/config.")
        sys.exit(1)

    reddit_id = extract_id(reddit_object)
    subreddit_name = settings.config["reddit"]["thread"]["subreddit"]
    original_title = reddit_object.get("thread_title", "")

    logger.info("Fetched story %s: '%s...'", reddit_id, original_title[:60])

    # ---- 4. Dedup check ----
    if is_already_posted(reddit_id):
        logger.info("Story %s already posted. Exiting.", reddit_id)
        sys.exit(0)

    # ---- 5. Extract and split the story text ----
    logger.info("Processing story text...")

    original_body = reddit_object.get("thread_post", "")
    if isinstance(original_body, list):
        original_body = " ".join(original_body)

    if not original_body or not original_body.strip():
        logger.error("Story body is empty. Aborting.")
        sys.exit(1)

    # Clean up basic Reddit artifacts
    import re
    story_text = re.sub(r'\[deleted\]|\[removed\]|\(?https?://\S+\)?', '', original_body)
    story_text = re.sub(r'&amp;', '&', story_text)
    story_text = re.sub(r'\s+', ' ', story_text).strip()

    # Split into sentences using spaCy
    from utils.posttextparser import posttextparser

    all_sentences = posttextparser(story_text)

    if not all_sentences:
        logger.error("No sentences extracted from story. Aborting.")
        sys.exit(1)

    # Use first sentence as the title/hook; rest as story body
    hook = all_sentences[0]
    body_sentences = all_sentences[1:] if len(all_sentences) > 1 else all_sentences[:]

    # Ensure at least one overlay image exists (FFmpeg needs at least one input)
    if not body_sentences:
        body_sentences = [hook]

    logger.info(
        "Story processed: %d sentences (hook: '%s...', %d body sentences)",
        len(all_sentences), hook[:50], len(body_sentences),
    )

    # Update reddit_object for the upstream pipeline
    reddit_object["thread_title"] = hook
    reddit_object["thread_post"] = body_sentences

    # ---- 6. TTS generation ----
    logger.info("Generating TTS audio...")
    from video_creation.voices import save_text_to_mp3

    length, number_of_clips = save_text_to_mp3(reddit_object)
    length = max(math.ceil(length), 1)
    logger.info("TTS complete: %ds duration, %d segments", length, number_of_clips)

    # ---- 7. Subtitle overlays (replace screenshots) ----
    logger.info("Generating subtitle overlay images...")
    from subtitle_generator import generate_subtitle_overlays

    temp_png_dir = f"assets/temp/{reddit_id}/png"
    if os.path.exists(temp_png_dir):
        shutil.rmtree(temp_png_dir)

    generate_subtitle_overlays(
        reddit_id=reddit_id,
        sentences=body_sentences,
        output_dir=temp_png_dir,
    )
    logger.info("Generated %d subtitle overlays.", len(body_sentences))

    # ---- 8. Background setup ----
    logger.info("Setting up background...")
    from video_creation.background import (
        chop_background,
        download_background_audio,
        download_background_video,
        get_background_config,
    )

    # Discover and register local MP4 backgrounds
    discover_local_backgrounds()

    bg_config = {
        "video": get_background_config("video"),
        "audio": get_background_config("audio"),
    }

    bg_name = bg_config.get("video", ("", "", "unknown"))[2] if isinstance(bg_config.get("video"), tuple) else "unknown"

    # Download and chop background
    try:
        download_background_video(bg_config["video"])
    except Exception as exc:
        logger.warning("Background video download failed: %s", exc)

    try:
        download_background_audio(bg_config["audio"])
    except Exception as exc:
        logger.warning("Background audio download failed: %s", exc)

    chop_background(bg_config, length, reddit_object)

    # ---- 9. Compose final video ----
    logger.info("Composing final video...")
    from video_creation.final_video import make_final_video

    os.makedirs("results", exist_ok=True)
    make_final_video(number_of_clips, length, reddit_object, bg_config)

    # ---- 10. Locate output ----
    result_files = glob.glob("results/**/*.mp4", recursive=True)
    if not result_files:
        logger.error("No output video found in results/!")
        sys.exit(1)

    latest_video = max(result_files, key=os.path.getmtime)
    video_size = os.path.getsize(latest_video)

    if video_size == 0:
        logger.error("Output video is empty: %s", latest_video)
        sys.exit(1)

    logger.info("Video generated: %s (%d bytes)", latest_video, video_size)

    # ---- 11. Captions ----
    tiktok_caption = select_caption(reddit_id)
    instagram_caption = f"{select_caption(reddit_id)}\n\n#reddit #storytime #aita #redditstories"
    youtube_title = f"Reddit Story: {hook[:90]}"
    youtube_description = f"{hook}\n\n#reddit #storytime #shorts"

    # ---- 12. Dry-run or upload ----
    if DRY_RUN or not PLATFORMS:
        logger.info("=" * 60)
        logger.info("[DRY RUN] — video would be uploaded:")
        logger.info("  Video:    %s", latest_video)
        logger.info("  TikTok:   %s", tiktok_caption)
        logger.info("  Instagram:%s", instagram_caption[:80])
        logger.info("  YouTube:  %s", youtube_title)
        logger.info("=" * 60)
        mark_posted(reddit_id, subreddit_name, "dry-run", bg_name, latest_video)
        from utils.cleanup import cleanup
        cleanup(reddit_id)
        sys.exit(0)

    # ---- 13. Upload to all platforms ----
    video_abs = os.path.abspath(latest_video)
    uploaded_any = False
    results = {}

    # TikTok
    if "tiktok" in PLATFORMS and TIKTOK_ACCOUNTNAME:
        logger.info("Uploading to TikTok...")
        from upload_tiktok import upload_video
        try:
            results["tiktok"] = upload_video(video_abs, tiktok_caption, TIKTOK_ACCOUNTNAME)
            uploaded_any = uploaded_any or results["tiktok"]
        except Exception as e:
            logger.error("TikTok upload error: %s", e)
            results["tiktok"] = False

    # Instagram
    if "instagram" in PLATFORMS and INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD:
        logger.info("Uploading to Instagram...")
        from upload_instagram import upload_to_instagram
        try:
            results["instagram"] = upload_to_instagram(
                video_abs, instagram_caption, INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD
            )
            uploaded_any = uploaded_any or results["instagram"]
        except Exception as e:
            logger.error("Instagram upload error: %s", e)
            results["instagram"] = False

    # YouTube
    if "youtube" in PLATFORMS:
        logger.info("Uploading to YouTube...")
        from upload_youtube import upload_to_youtube
        try:
            results["youtube"] = upload_to_youtube(
                video_abs,
                title=youtube_title,
                description=youtube_description,
            )
            uploaded_any = uploaded_any or results["youtube"]
        except Exception as e:
            logger.error("YouTube upload error: %s", e)
            results["youtube"] = False

    logger.info("Upload results: %s", json.dumps(results))

    if not uploaded_any:
        logger.error("No successful uploads. Story NOT marked as posted.")
        sys.exit(1)

    # ---- 14. Finalize ----
    mark_posted(reddit_id, subreddit_name, str(results), bg_name, latest_video)
    from utils.cleanup import cleanup
    cleanup(reddit_id)
    logger.info("Pipeline completed! Results: %s", json.dumps(results))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
        sys.exit(1)
    except Exception:
        logger.exception("Pipeline failed with unhandled exception.")
        traceback.print_exc()
        sys.exit(1)

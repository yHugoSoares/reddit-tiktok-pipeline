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

# ── Mock Reddit stories ──
STORIES = [
    {
        "title": "AITA for telling my roommate her boyfriend can't live with us rent-free?",
        "body": (
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
        ),
    },
    {
        "title": "AITA for exposing my sister's affair at her wedding?",
        "body": (
            "My sister Jessica has been engaged to Mark for three years. Everyone loved Mark. He was "
            "the perfect son-in-law, always helping my parents with things around the house, showing up "
            "to every family dinner, remembering every birthday. Two months before the wedding I went "
            "to visit Jessica at her apartment and found her with another man. It was her coworker David. "
            "She begged me not to tell anyone. She said it was cold feet and that she loved Mark and "
            "the affair was already over. I kept her secret for weeks but it was eating me alive. "
            "Mark would come over and talk about how excited he was to start a family with her. "
            "He had already put down a deposit on a house for them. At the wedding reception during "
            "the speeches I stood up. I didn't plan to say anything. I was going to give a normal toast. "
            "But when I looked at Mark beaming at her, I just could not hold it in anymore. I told "
            "everyone what I had seen. The room went silent. Jessica burst into tears. Mark just walked "
            "out without saying a word. My parents are furious with me. They said I ruined her life "
            "and humiliated the family. Jessica won't speak to me. My mom says I should have let "
            "her make her own mistakes. But was I supposed to just let Mark marry someone who was "
            "cheating on him? Was I supposed to smile and give a toast and pretend everything was fine? "
            "I feel like I did the right thing but nobody in my family agrees with me. I have not "
            "spoken to any of them in three weeks. My dad sent me a text saying I am no longer "
            "welcome at family gatherings until I apologize to Jessica. I refuse to apologize. "
            "But being cut off from my entire family is starting to make me wonder if I went too far."
        ),
    },
    {
        "title": "AITA for refusing to give my brother my inheritance even though he has kids?",
        "body": (
            "My grandmother passed away six months ago and left me seventy thousand dollars. "
            "I was very close to her growing up. She basically raised me while my parents were "
            "working three jobs each to keep us afloat. My brother was always closer to my dad's "
            "side of the family and barely visited her. He would show up at Christmas for presents "
            "and leave within an hour. When she was in the hospital for the last three weeks of her "
            "life, I was there every single day. I took time off work. I read to her. I held her "
            "hand. My brother visited once for about twenty minutes and spent most of it on his phone. "
            "When the will was read and I got the money, my brother lost his mind. He said it was not "
            "fair because he has three kids and I am single. He said the money should go to the family "
            "and by family he meant his family. He suggested that maybe our grandmother was not in her "
            "right mind when she wrote the will and that I might have manipulated her. That accusation "
            "made my blood boil. I told him absolutely not. I am not giving him a single cent. "
            "I am using the money to go back to school and finish my degree. My parents say I should "
            "at least give him something to keep the peace. They said ten thousand dollars would be "
            "enough to help with his kids' school fees. I told them that if our grandmother wanted "
            "him to have ten thousand dollars she would have written it in the will. She did not. "
            "She left him a watch and some old photographs. That was her choice. Now the whole "
            "extended family is weighing in. My aunt called me selfish. My uncle said I am punishing "
            "innocent children for a grudge against their father. But I am not punishing anyone. "
            "I am just keeping what was given to me by someone who actually valued my presence "
            "in her life. My grandmother knew exactly what she was doing. She saw who showed up "
            "and who did not. I do not think I should have to pay my brother to pretend he cared."
        ),
    },
]

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
def process_story(story_title: str, story_body: str, story_index: int):
    """Generate a video for one mock story."""
    import hashlib
    import re as _re
    from utils.posttextparser import posttextparser

    text = _re.sub(r'\[deleted\]|\[removed\]|\(?https?://\S+\)?', '', story_body)
    text = _re.sub(r'&amp;', '&', text)
    text = _re.sub(r'\s+', ' ', text).strip()

    all_sentences = posttextparser(text)
    if not all_sentences:
        logger.error("Story %d: no sentences extracted.", story_index)
        return

    hook = all_sentences[0]
    body_sentences = all_sentences[1:] if len(all_sentences) > 1 else all_sentences[:]
    if not body_sentences:
        body_sentences = [hook]

    reddit_id = hashlib.md5(story_title.encode()).hexdigest()[:8]
    subreddit = os.environ.get("REDDIT_SUBREDDIT", "AmItheAsshole")

    reddit_object = {
        "thread_id": reddit_id,
        "thread_url": f"https://reddit.com/r/{subreddit}/comments/{reddit_id}",
        "thread_title": hook,
        "thread_post": body_sentences,
        "comments": [],
        "post_url": f"https://reddit.com/r/{subreddit}/comments/{reddit_id}",
    }

    logger.info("Story %d/%d: '%s...' (%d chars, %d sentences)",
                 story_index + 1, len(STORIES), hook[:60], len(text), len(all_sentences))

    logger.info("Story %d: TTS...", story_index + 1)
    from video_creation.voices import save_text_to_mp3
    length, number_of_clips = save_text_to_mp3(reddit_object)
    length = max(math.ceil(length), 1)
    logger.info("Story %d: %ds, %d segments", story_index + 1, length, number_of_clips)

    logger.info("Story %d: subtitles...", story_index + 1)
    from subtitle_generator import generate_subtitle_overlays
    temp_png = f"assets/temp/{reddit_id}/png"
    if os.path.exists(temp_png):
        shutil.rmtree(temp_png)
    generate_subtitle_overlays(reddit_id, body_sentences, temp_png)

    logger.info("Story %d: background...", story_index + 1)
    from video_creation.background import (
        chop_background, download_background_audio,
        download_background_video, get_background_config, register_local_backgrounds,
    )
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

    logger.info("Story %d: rendering...", story_index + 1)
    from video_creation.final_video import make_final_video
    os.makedirs("results", exist_ok=True)
    make_final_video(number_of_clips, length, reddit_object, bg_config)

    result_files = glob.glob("results/**/*.mp4", recursive=True)
    if result_files:
        latest = max(result_files, key=os.path.getmtime)
        size = os.path.getsize(latest)
        logger.info("Story %d video: %s (%d MB)", story_index + 1, latest, size // (1024 * 1024))

    from utils.cleanup import cleanup
    cleanup(reddit_id)


def main():
    from init_config import generate
    generate()

    import toml as _toml
    from utils import settings
    settings.config = _toml.load("config.toml")
    settings.config["settings"]["storymode"] = True
    settings.config["settings"]["storymodemethod"] = 1
    if settings.config["settings"].get("storymode_max_length", 1000) < 5000:
        settings.config["settings"]["storymode_max_length"] = 5000

    for i, story in enumerate(STORIES):
        logger.info("=" * 50)
        logger.info("PROCESSING STORY %d/%d", i + 1, len(STORIES))
        logger.info("=" * 50)
        process_story(story["title"], story["body"], i)

    logger.info("DONE — %d videos generated.", len(STORIES))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Auto-generate config.toml from environment variables.

Run once before the pipeline to create the Reddit config non-interactively.
Falls back to interactive prompts if required env vars are missing.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

CONFIG_PATH = Path("config.toml")


def generate():
    # If config already exists and looks valid, skip
    if CONFIG_PATH.exists() and CONFIG_PATH.stat().st_size > 100:
        print(f"{CONFIG_PATH} already exists ({CONFIG_PATH.stat().st_size} bytes). Skipping.")
        return

    # Check required env vars
    required = ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USERNAME", "REDDIT_PASSWORD"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"Missing required env vars: {', '.join(missing)}")
        print("Set them in .env or your environment, then re-run.")
        print("Falling back to interactive setup...")
        from utils import settings
        settings.check_toml("utils/.config.template.toml", "config.toml")
        return

    subreddit = os.environ.get("REDDIT_SUBREDDIT", "AmItheAsshole")
    tts_choice = os.environ.get("TTS_CHOICE", "googletranslate")
    story_max = int(os.environ.get("STORY_MAX_LENGTH", "10000"))
    background = os.environ.get("BACKGROUND_VIDEO", "")
    elevenlabs_key = os.environ.get("ELEVENLABS_API_KEY", "")
    elevenlabs_voice = os.environ.get("ELEVENLABS_VOICE_ID", "Bella")

    config = f'''[reddit.creds]
client_id = "{os.environ['REDDIT_CLIENT_ID']}"
client_secret = "{os.environ['REDDIT_CLIENT_SECRET']}"
username = "{os.environ['REDDIT_USERNAME']}"
password = "{os.environ['REDDIT_PASSWORD']}"
2fa = false

[reddit.thread]
random = true
subreddit = "{subreddit}"
post_id = ""
max_comment_length = 500
min_comment_length = 1
post_lang = ""
min_comments = 20
blocked_words = ""

[ai]
ai_similarity_enabled = false
ai_similarity_keywords = ""

[settings]
allow_nsfw = false
theme = "dark"
times_to_run = 1
opacity = 0.9
storymode = true
storymodemethod = 1
storymode_max_length = {story_max}
resolution_w = 1080
resolution_h = 1920
zoom = 1
channel_name = "Reddit Stories"

[settings.background]
background_video = "{background}"
background_audio = ""
background_audio_volume = 0.0
enable_extra_audio = false
background_thumbnail = false
background_thumbnail_font_family = "arial"
background_thumbnail_font_size = 96
background_thumbnail_font_color = "255,255,255"

[settings.tts]
voice_choice = "{tts_choice}"
random_voice = false
elevenlabs_voice_name = "{elevenlabs_voice}"
elevenlabs_api_key = "{elevenlabs_key}"
aws_polly_voice = "Matthew"
streamlabs_polly_voice = "Matthew"
tiktok_voice = "en_us_001"
tiktok_sessionid = ""
python_voice = "1"
py_voice_num = "2"
silence_duration = 0.3
no_emojis = false
openai_api_url = "https://api.openai.com/v1/"
openai_api_key = ""
openai_voice_name = "alloy"
openai_model = "tts-1"
'''

    CONFIG_PATH.write_text(config, encoding="utf-8")
    print(f"config.toml auto-generated for r/{subreddit} with {tts_choice} TTS.")


if __name__ == "__main__":
    generate()

"""Instagram Reels upload via instagrapi.

Handles login session persistence in assets/cookies/instagram/.
"""

import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

SESSION_DIR = Path("assets/cookies/instagram")
SESSION_FILE = SESSION_DIR / "session.json"


def upload_to_instagram(video_path: str, caption: str, username: str, password: str) -> bool:
    """Upload a video as an Instagram Reel.

    Args:
        video_path: Path to the MP4 file.
        caption: Video caption.
        username: Instagram username.
        password: Instagram password.

    Returns:
        True if upload confirmed, False otherwise.
    """
    if not os.path.exists(video_path):
        logger.error("Video not found: %s", video_path)
        return False

    if not username or not password:
        logger.warning("Instagram credentials not set. Skipping Instagram upload.")
        return False

    try:
        from instagrapi import Client
        from instagrapi.exceptions import LoginRequired
    except ImportError:
        logger.warning("instagrapi not installed. Skipping Instagram upload.")
        return False

    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    client = Client()

    # Try loading existing session
    if SESSION_FILE.exists():
        try:
            client.load_settings(SESSION_FILE)
            client.login(username, password)
            client.get_timeline_feed()  # Verify session is alive
            logger.info("Instagram session loaded from cache.")
        except (LoginRequired, Exception):
            logger.info("Instagram session expired. Re-logging in...")
            SESSION_FILE.unlink(missing_ok=True)

    # Fresh login
    if not SESSION_FILE.exists():
        try:
            client.login(username, password)
            client.dump_settings(SESSION_FILE)
            logger.info("Instagram login successful. Session saved.")
        except Exception as e:
            logger.error("Instagram login failed: %s", e)
            return False

    # Upload as Reel
    for attempt in range(3):
        try:
            logger.info("Uploading Reel to Instagram (attempt %d/3)...", attempt + 1)
            client.clip_upload(
                path=video_path,
                caption=caption,
            )
            logger.info("Instagram Reel uploaded successfully!")
            return True
        except LoginRequired:
            logger.warning("Instagram session expired. Re-logging in...")
            SESSION_FILE.unlink(missing_ok=True)
            try:
                client.login(username, password)
                client.dump_settings(SESSION_FILE)
            except Exception as e:
                logger.error("Instagram re-login failed: %s", e)
                return False
        except Exception as e:
            logger.error("Instagram upload attempt %d failed: %s", attempt + 1, e)
            if attempt < 2:
                time.sleep(30 * (attempt + 1))

    return False

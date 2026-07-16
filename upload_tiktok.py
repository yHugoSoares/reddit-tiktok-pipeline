"""TikTok upload integration via tiktokautouploader.

Handles cookie persistence, retry logic, and error reporting.
"""  

import os
import time
import logging

logger = logging.getLogger(__name__)


def upload_video(video_path: str, caption: str, accountname: str) -> bool:
    """Upload a video to TikTok using tiktokautouploader.

    Args:
        video_path: Absolute path to the MP4 file.
        caption: TikTok caption/description text.
        accountname: TikTok account username.

    Returns:
        True if upload was confirmed successful, False otherwise.
    """
    if not os.path.exists(video_path):
        logger.error("Video file not found: %s", video_path)
        return False

    if not accountname:
        logger.error("TIKTOK_ACCOUNTNAME not set. Cannot upload.")
        return False

    # Save/load cookies from assets/cookies/
    original_cwd = os.getcwd()
    cookie_dir = os.path.join(original_cwd, "assets", "cookies")
    os.makedirs(cookie_dir, exist_ok=True)

    try:
        os.chdir(cookie_dir)

        from tiktokautouploader import upload_tiktok, TikTokUploadError

        for attempt in range(3):
            try:
                logger.info("Upload attempt %d/3 to account '%s' ...", attempt + 1, accountname)
                result = upload_tiktok(
                    video=video_path,
                    description=caption,
                    accountname=accountname,
                    headless=True,
                    stealth=True,
                    suppressprint=False,
                )
                if result == "Completed":
                    logger.info("TikTok upload confirmed successful.")
                    return True

                logger.warning("Upload returned unexpected result: %s", result)

            except TikTokUploadError as exc:
                logger.error("TikTok upload error (attempt %d): %s", attempt + 1, exc)
                if attempt < 2:
                    wait = 30 * (attempt + 1)
                    logger.info("Retrying in %ds ...", wait)
                    time.sleep(wait)
                else:
                    break

            except Exception:
                logger.exception("Unexpected upload failure (attempt %d)", attempt + 1)
                if attempt < 2:
                    time.sleep(30)
                else:
                    break

        return False

    finally:
        os.chdir(original_cwd)

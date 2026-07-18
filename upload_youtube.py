"""YouTube Shorts upload via YouTube Data API v3.

Requires a Google Cloud project with YouTube Data API v3 enabled
and OAuth2 credentials in assets/cookies/youtube/client_secret.json.

First-time setup will trigger an OAuth browser flow.
Refresh tokens are persisted for subsequent runs.
"""

import logging
import os
import pickle
import time
from pathlib import Path

logger = logging.getLogger(__name__)

TOKEN_DIR = Path("assets/cookies/youtube")
TOKEN_FILE = TOKEN_DIR / "token.pickle"
CLIENT_SECRET_FILE = TOKEN_DIR / "client_secret.json"

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _get_authenticated_service():
    """Authenticate with YouTube API, caching credentials."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        logger.warning("Google API packages not installed. Skipping YouTube.")
        return None

    TOKEN_DIR.mkdir(parents=True, exist_ok=True)

    credentials = None

    # Load cached token
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, "rb") as f:
                credentials = pickle.load(f)
        except Exception:
            TOKEN_FILE.unlink(missing_ok=True)

    # Refresh or re-auth
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                logger.info("YouTube token refreshed.")
            except Exception:
                credentials = None

        if not credentials:
            if not CLIENT_SECRET_FILE.exists():
                logger.error(
                    "YouTube client_secret.json not found at %s. "
                    "Download it from Google Cloud Console → APIs & Services → Credentials.",
                    CLIENT_SECRET_FILE,
                )
                return None

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET_FILE), SCOPES
            )
            # Run local server for OAuth callback
            credentials = flow.run_local_server(port=0)

        # Save token
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(credentials, f)
        logger.info("YouTube credentials saved to %s.", TOKEN_FILE)

    return build("youtube", "v3", credentials=credentials)


def upload_to_youtube(
    video_path: str,
    title: str,
    description: str,
    tags: list = None,
    category: str = "24",  # Entertainment
    privacy: str = "public",
    made_for_kids: bool = False,
    self_declared: bool = False,
) -> bool:
    """Upload a video as a YouTube Short.

    Videos under 60s with vertical 9:16 aspect ratio are automatically
    categorized as Shorts.

    Returns True on success.
    """
    if not os.path.exists(video_path):
        logger.error("Video not found: %s", video_path)
        return False

    youtube = _get_authenticated_service()
    if youtube is None:
        return False

    if tags is None:
        tags = ["reddit", "storytime", "shorts"]

    title = title[:100]  # YouTube limits titles to 100 chars

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category,
        },
        "status": {
            "privacyStatus": privacy,
            "madeForKids": made_for_kids,
            "selfDeclaredMadeForKids": self_declared,
        },
    }

    for attempt in range(3):
        try:
            logger.info("Uploading to YouTube Shorts (attempt %d/3)...", attempt + 1)
            request = youtube.videos().insert(
                part=",".join(body.keys()),
                body=body,
                media_body=video_path,
            )
            response = request.execute()
            video_id = response.get("id", "unknown")
            logger.info("YouTube upload complete! Video ID: %s", video_id)
            return True
        except Exception as e:
            logger.error("YouTube upload attempt %d failed: %s", attempt + 1, e)
            if attempt < 2:
                time.sleep(30 * (attempt + 1))

    return False

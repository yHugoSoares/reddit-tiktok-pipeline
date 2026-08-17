"""Generate reactive (karaoke) subtitle clips from edge-tts word timings.

EdgeTTS now writes a ``.words.json`` sidecar next to every MP3 it produces
(a list of ``[start_s, end_s, word]``). This module reads those sidecars,
builds one karaoke video clip per sentence, and drops them into
``assets/temp/<id>/karaoke/`` where ``final_video.py`` picks them up.
"""

import json
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def load_word_timings(mp3_dir: str, index: int) -> list:
    """Load the word timings sidecar for postaudio-<index>.mp3."""
    sidecar = f"{mp3_dir}/postaudio-{index}.mp3.words.json"
    if not Path(sidecar).is_file():
        return []
    try:
        with open(sidecar, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def mp3_duration(path: str) -> float:
    """Return the audio duration of an MP3 in seconds."""
    try:
        import ffmpeg
        info = ffmpeg.probe(path)
        return float(info["format"]["duration"])
    except Exception:
        return 0.0


def generate_karaoke_for_reddit(
    reddit_id: str,
    body_sentences: list,
    temp_root: str = "assets/temp",
) -> int:
    """Build karaoke clips for every body sentence of a Reddit story.

    Args:
        reddit_id: Reddit post ID (used for the temp folder).
        body_sentences: List of body sentences (parallel to postaudio-N.mp3).
        temp_root: Base temp directory.

    Returns:
        Number of karaoke clips generated.
    """
    from subtitle_generator import generate_karaoke_clips

    mp3_dir = f"{temp_root}/{reddit_id}/mp3"
    karaoke_dir = f"{temp_root}/{reddit_id}/karaoke"

    if not Path(mp3_dir).is_dir():
        logger.info("No MP3 dir %s — skipping karaoke.", mp3_dir)
        return 0

    word_timings = []
    sentence_durations = []
    usable = []

    for i, sentence in enumerate(body_sentences):
        timings = load_word_timings(mp3_dir, i)
        if not timings:
            logger.info("No word timings for sentence %d — skipping karaoke for it.", i)
            continue
        dur = mp3_duration(f"{mp3_dir}/postaudio-{i}.mp3")
        if dur <= 0:
            continue
        word_timings.append(timings)
        sentence_durations.append(dur)
        usable.append(sentence)

    if not usable:
        logger.info("No usable word timings — using static subtitles.")
        return 0

    if Path(karaoke_dir).is_dir():
        import shutil
        shutil.rmtree(karaoke_dir)

    clips = generate_karaoke_clips(
        reddit_id=reddit_id,
        sentences=usable,
        word_timings=word_timings,
        sentence_durations=sentence_durations,
        output_dir=karaoke_dir,
    )
    logger.info("Generated %d karaoke clips in %s.", len(clips), karaoke_dir)
    return len(clips)
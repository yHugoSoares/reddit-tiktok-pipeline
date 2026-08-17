"""Generate burned-in subtitle overlay images for TikTok videos.

Creates high-contrast PNG text overlays with transparent backgrounds,
white text, and black shadow outlines — mobile-readable on any gameplay.
"""

import os
import textwrap
from pathlib import Path


def generate_subtitle_overlays(
    reddit_id: str,
    sentences: list,
    output_dir: str,
    resolution: tuple = (1080, 1920),
    font_path: str = "fonts/Roboto-Bold.ttf",
    font_size: int = 150,
    text_color: tuple = (255, 255, 255, 255),
    shadow_color: tuple = (0, 0, 0, 255),
    bg_color: tuple = (0, 0, 0, 0),
    wrap_width: int = 14,
) -> list:
    """Generate timed subtitle overlay PNGs for each sentence.

    Images are RGBA with transparent background, big bold white text,
    and a thick black outline — the classic TikTok caption style.

    Args:
        reddit_id: Reddit post ID (for naming).
        sentences: List of story sentences.
        output_dir: Directory to save PNG files.
        resolution: (width, height) of output images.
        font_path: Path to TTF font file.
        font_size: Font size in points.
        text_color: RGBA tuple for main text.
        shadow_color: RGBA tuple for outline.
        bg_color: RGBA tuple for background.
        wrap_width: Characters per line before wrapping.

    Returns:
        List of file paths to generated PNG files.
    """
    from PIL import Image, ImageDraw, ImageFont

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(font_path, font_size)
    img_w, img_h = resolution
    stroke_width = max(8, font_size // 12)

    overlay_paths = []

    for i, sentence in enumerate(sentences):
        if not sentence or not sentence.strip():
            continue

        # Create transparent RGBA image
        img = Image.new("RGBA", resolution, bg_color)
        draw = ImageDraw.Draw(img)

        # Word-wrap text into lines
        lines = textwrap.wrap(sentence.strip(), width=wrap_width)
        if not lines:
            continue

        # Calculate text block dimensions
        line_height = font_size + 20
        total_height = len(lines) * line_height

        # Position in lower third (TikTok-safe area, above any UI elements)
        start_y = img_h - total_height - 220

        # Draw each line centered horizontally
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_width = bbox[2] - bbox[0]
            x = (img_w - line_width) // 2

            # Thick black outline (TikTok caption look)
            draw.text((x, start_y), line, font=font, fill=text_color,
                      stroke_width=stroke_width, stroke_fill=shadow_color)
            start_y += line_height

        filepath = os.path.join(output_dir, f"img{i}.png")
        img.save(filepath)
        overlay_paths.append(filepath)

    return overlay_paths


def render_title_overlay(
    title: str,
    output_path: str,
    resolution: tuple = (1080, 1920),
    font_path: str = "fonts/Roboto-Bold.ttf",
    font_size: int = 56,
    text_color: tuple = (255, 255, 255, 255),
    shadow_color: tuple = (0, 0, 0, 180),
    bg_color: tuple = (0, 0, 0, 0),
    wrap_width: int = 22,
) -> str:
    """Generate a title card overlay PNG.

    Returns path to the generated file.
    """
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(font_path, font_size)
    img_w, img_h = resolution
    img = Image.new("RGBA", resolution, bg_color)
    draw = ImageDraw.Draw(img)

    lines = textwrap.wrap(title.strip(), width=wrap_width)
    if not lines:
        return output_path

    line_height = font_size + 15
    total_height = len(lines) * line_height
    start_y = (img_h - total_height) // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        x = (img_w - line_width) // 2

        for dx, dy in [
            (-3, -3), (-3, 3), (3, -3), (3, 3),
            (0, -3), (0, 3), (-3, 0), (3, 0),
        ]:
            draw.text((x + dx, start_y + dy), line, font=font, fill=shadow_color)
        draw.text((x, start_y), line, font=font, fill=text_color)
        start_y += line_height

    img.save(output_path)
    return output_path


# ---------------------------------------------------------------------------
# Reactive (karaoke) subtitles — highlight each word while it is spoken
# ---------------------------------------------------------------------------

_ACCENT = (255, 190, 60, 255)  # golden — pops against any gameplay


def _wrap_tokens(tokens, wrap_width):
    """Wrap a token list into lines of ~wrap_width characters, keeping token order."""
    lines, cur, cur_len = [], [], 0
    for tok in tokens:
        add = len(tok) + (1 if cur else 0)
        if cur and cur_len + add > wrap_width:
            lines.append(cur)
            cur, cur_len = [tok], len(tok)
        else:
            cur.append(tok)
            cur_len += add
    if cur:
        lines.append(cur)
    return lines


def _render_token_line(draw, font, line, y, img_w, highlight_index=None, fill=(255, 255, 255, 255), stroke_width=12):
    """Draw one wrapped line, centered; optionally highlight the token at highlight_index."""
    # Measure the full line width first so we can center it (no trailing space)
    widths = [draw.textlength(tok, font=font) for tok in line]
    total_w = sum(widths) + (len(line) - 1) * draw.textlength(" ", font=font)
    x = max((img_w - total_w) // 2, 0)
    for idx, tok in enumerate(line):
        tok_fill = _ACCENT if idx == highlight_index else fill
        draw.text((x, y), tok, font=font, fill=tok_fill,
                  stroke_width=stroke_width, stroke_fill=(0, 0, 0, 255))
        x += widths[idx] + draw.textlength(" ", font=font)
    return x


def generate_karaoke_clips(
    reddit_id: str,
    sentences: list,
    word_timings: list,
    sentence_durations: list,
    output_dir: str,
    resolution: tuple = (1080, 1920),
    font_path: str = "fonts/Roboto-Bold.ttf",
    font_size: int = 150,
    wrap_width: int = 10,
):
    """Build one karaoke video clip per sentence.

    Each word is rendered as its own frame (current word highlighted in
    golden), and the frames are concatenated with the exact timing from
    edge-tts so the highlight follows the narration.

    Args:
        reddit_id: Reddit post ID (temp folder).
        sentences: Body sentences (parallel to postaudio-N.mp3).
        word_timings: List of [[start_s, end_s, word], ...] per sentence.
        sentence_durations: Audio duration in seconds per sentence.
        output_dir: Directory to write clips into.
    """
    import json
    import os
    import subprocess
    from PIL import Image, ImageDraw, ImageFont

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(font_path, font_size)
    img_w, img_h = resolution
    stroke_width = max(10, font_size // 10)

    clips = []
    for i, (sentence, timings, dur) in enumerate(zip(sentences, word_timings, sentence_durations)):
        if not timings or dur <= 0:
            continue
        tokens = [t[2] for t in timings]
        raw_durs = [max(t[1] - t[0], 0.05) for t in timings]
        # Scale so the frames exactly fill the sentence audio duration
        total_raw = sum(raw_durs)
        factor = dur / total_raw if total_raw > 0 else 1.0
        durs = [d * factor for d in raw_durs]
        if durs:
            durs[-1] = dur - sum(durs[:-1])

        lines = _wrap_tokens(tokens, wrap_width)
        line_height = font_size + 22
        total_height = len(lines) * line_height
        start_y = img_h - total_height - 220

        # Token -> (line_idx, col_idx) mapping
        token_pos = {}
        pos = 0
        for li, line in enumerate(lines):
            for ci, tok in enumerate(line):
                token_pos[pos] = (li, ci)
                pos += 1

        png_dir = os.path.join(output_dir, f"s{i}_frames")
        Path(png_dir).mkdir(parents=True, exist_ok=True)
        frames = []
        concat_lines = ["ffconcat version 1.0"]
        for j, (tok, d) in enumerate(zip(tokens, durs)):
            frame_path = os.path.join(png_dir, f"w{j}.png")
            img = Image.new("RGBA", resolution, (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            y = start_y
            hi_li, hi_ci = token_pos.get(j, (0, -1))
            for li, line in enumerate(lines):
                _render_token_line(draw, font, line, y, img_w,
                                   highlight_index=hi_ci if li == hi_li else None,
                                   stroke_width=stroke_width)
                y += line_height
            img.save(frame_path)
            frames.append(frame_path)
            # Relative paths (concat demuxer resolves them against the list file)
            concat_lines.append(f"file s{i}_frames/w{j}.png")
            concat_lines.append(f"duration {d:.4f}")

        # Last frame must hold until the clip ends
        if frames:
            concat_lines.append(f"file s{i}_frames/w{len(frames) - 1}.png")
            concat_lines.append("duration 0.001")

        list_file = os.path.join(output_dir, f"s{i}.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            f.write("\n".join(concat_lines))

        clip_path = os.path.join(output_dir, f"s{i}.mkv")
        # PNG codec in MKV preserves the alpha channel for later overlay
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", f"s{i}.txt",
            "-c:v", "png", f"s{i}.mkv",
        ]
        subprocess.run(cmd, check=True, cwd=output_dir)
        clips.append(clip_path)

    return clips

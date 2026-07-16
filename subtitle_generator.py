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
    font_size: int = 68,
    text_color: tuple = (255, 255, 255, 255),
    shadow_color: tuple = (0, 0, 0, 180),
    bg_color: tuple = (0, 0, 0, 0),
    wrap_width: int = 20,
) -> list:
    """Generate timed subtitle overlay PNGs for each sentence.

    Images are RGBA with transparent background, white text,
    and black shadow for readability over any gameplay background.

    Args:
        reddit_id: Reddit post ID (for naming).
        sentences: List of story sentences.
        output_dir: Directory to save PNG files.
        resolution: (width, height) of output images.
        font_path: Path to TTF font file.
        font_size: Font size in points.
        text_color: RGBA tuple for main text.
        shadow_color: RGBA tuple for text shadow/outline.
        bg_color: RGBA tuple for background.
        wrap_width: Characters per line before wrapping.

    Returns:
        List of file paths to generated PNG files.
    """
    from PIL import Image, ImageDraw, ImageFont

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(font_path, font_size)
    img_w, img_h = resolution

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
        line_height = font_size + 12
        total_height = len(lines) * line_height

        # Position in lower third (TikTok-safe area, above any UI elements)
        start_y = img_h - total_height - 180

        # Draw each line centered horizontally
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_width = bbox[2] - bbox[0]
            x = (img_w - line_width) // 2

            # Draw shadow/outline (8 directions for readability)
            for dx, dy in [
                (-3, -3), (-3, 3), (3, -3), (3, 3),
                (0, -3), (0, 3), (-3, 0), (3, 0),
            ]:
                draw.text((x + dx, start_y + dy), line, font=font, fill=shadow_color)

            # Draw main text
            draw.text((x, start_y), line, font=font, fill=text_color)
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

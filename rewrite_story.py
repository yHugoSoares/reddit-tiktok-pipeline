"""DeepSeek script rewrite integration.

Calls DeepSeek API (OpenAI-compatible) to rewrite a Reddit story
for TikTok narration. Returns plain rewritten text.
"""

import os
import logging

logger = logging.getLogger(__name__)

DEEPSEEK_SYSTEM_PROMPT = (
    "You are a TikTok story narration writer. Output only the narration text."
)

DEEPSEEK_USER_PROMPT = """Rewrite this Reddit story for a TikTok story narration.

Rules:
- Keep it in first person if the original is first person.
- Start with a strong 1-sentence hook.
- Keep the underlying meaning and key events intact.
- Use short sentences that work well as burned-in subtitles.
- Remove filler, repetition, usernames, links, and irrelevant metadata.
- Do not invent facts.
- Keep it appropriate for a general TikTok audience.
- Output only the narration text. Do not add labels, commentary, markdown, or a title.

Story:
{reddit_story_text}"""


def deepseek_rewrite(title: str, body: str, story_id: str = "") -> str:
    """Rewrite a Reddit story using DeepSeek.

    Args:
        title: Reddit post title.
        body: Reddit post selftext (full body).
        story_id: Reddit post ID for logging.

    Returns:
        Rewritten narration text, or original combined text as fallback.
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    combined = f"{title}\n\n{body}" if body else title
    original_length = len(combined)

    if not api_key:
        logger.warning("DEEPSEEK_API_KEY not set. Using original text as fallback.")
        return combined

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

        for attempt in range(2):
            try:
                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": DEEPSEEK_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": DEEPSEEK_USER_PROMPT.format(
                                reddit_story_text=combined
                            ),
                        },
                    ],
                    temperature=0.7,
                    max_tokens=2000,
                )
                rewritten = response.choices[0].message.content.strip()
                if not rewritten:
                    raise ValueError("DeepSeek returned empty response")

                logger.info(
                    "Story %s rewritten: %d → %d chars",
                    story_id,
                    original_length,
                    len(rewritten),
                )
                return rewritten

            except Exception as exc:
                logger.error(
                    "DeepSeek attempt %d failed for story %s: %s",
                    attempt + 1,
                    story_id,
                    exc,
                )
                if attempt == 1:
                    logger.warning(
                        "DeepSeek rewrite failed after 2 attempts. "
                        "Falling back to original text."
                    )

        return combined

    except ImportError:
        logger.warning("openai package not installed. Using original text.")
        return combined

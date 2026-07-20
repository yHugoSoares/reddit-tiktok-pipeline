"""Microsoft Edge TTS — free neural voices, no API key.

Uses edge-tts package. All voices: https://github.com/rany2/edge-tts
"""

import asyncio
import random

from utils import settings


class EdgeTTS:
    def __init__(self):
        self.max_chars = 1000

    def run(self, text, filepath, random_voice: bool = False):
        voice = self.randomvoice() if random_voice else self._get_voice()

        async def _save():
            import edge_tts
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(filepath)

        asyncio.run(_save())

    def randomvoice(self):
        return random.choice(_NEURAL_VOICES)

    def _get_voice(self):
        voice = settings.config["settings"]["tts"].get("edge_voice", "en-US-AriaNeural")
        return voice if voice in _NEURAL_VOICES else "en-US-AriaNeural"


# English neural voices — all female (popular for TikTok narration)
_NEURAL_VOICES = [
    "en-US-AriaNeural",    # Warm, engaging — best for storytelling
    "en-US-JennyNeural",   # Cheerful, conversational
    "en-US-SoniaNeural",   # British accent
    "en-GB-SoniaNeural",   # British female
    "en-GB-LibbyNeural",   # British, articulate
    "en-US-AnaNeural",     # Child-like, cute
    "en-US-MichelleNeural",# Friendly
    "en-AU-NatashaNeural", # Australian
]

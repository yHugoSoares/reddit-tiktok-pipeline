"""Microsoft Edge TTS — free neural voices, no API key.

Uses edge-tts package. All voices: https://github.com/rany2/edge-tts
"""

import asyncio
import json
import random
from pathlib import Path

from utils import settings


class EdgeTTS:
    def __init__(self):
        self.max_chars = 1000

    def run(self, text, filepath, random_voice: bool = False):
        """Synthesize speech, saving the MP3 and a per-word timing JSON sidecar.

        The sidecar file is ``<filepath>.words.json`` and contains a list of
        ``[start_seconds, end_seconds, word]`` tuples so the renderer can
        highlight each word while it is being spoken.
        """
        voice = self.randomvoice() if random_voice else self._get_voice()
        asyncio.run(self._synthesize(text, voice, filepath))

    async def _synthesize(self, text, voice, filepath):
        import edge_tts
        from edge_tts.submaker import SubMaker

        communicate = edge_tts.Communicate(text, voice, boundary="WordBoundary")
        submaker = SubMaker()
        with open(filepath, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    submaker.feed(chunk)

        words = [
            [cue.start.total_seconds(), cue.end.total_seconds(), cue.content]
            for cue in submaker.cues
        ]
        sidecar = f"{filepath}.words.json"
        Path(sidecar).write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")

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

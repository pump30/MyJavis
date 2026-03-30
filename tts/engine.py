"""Text-to-speech engine using edge-tts with pyttsx3 fallback."""

import asyncio
import re
import config


def _detect_language(text: str) -> str:
    """Simple heuristic: if text contains CJK characters, treat as Chinese."""
    cjk = re.findall(r'[\u4e00-\u9fff]', text)
    return "zh" if len(cjk) > len(text) * 0.3 else "en"


def _clean_for_speech(text: str) -> str:
    """Remove emoji, markdown symbols, and other non-speech characters."""
    # Remove emoji (Unicode emoji ranges)
    text = re.sub(
        r'[\U0001F600-\U0001F64F'   # emoticons
        r'\U0001F300-\U0001F5FF'     # symbols & pictographs
        r'\U0001F680-\U0001F6FF'     # transport & map
        r'\U0001F1E0-\U0001F1FF'     # flags
        r'\U00002702-\U000027B0'     # dingbats
        r'\U0000FE00-\U0000FE0F'     # variation selectors
        r'\U0001F900-\U0001F9FF'     # supplemental symbols
        r'\U0001FA00-\U0001FA6F'     # chess symbols
        r'\U0001FA70-\U0001FAFF'     # symbols extended
        r'\U00002600-\U000026FF'     # misc symbols
        r'\U0000200D'                # zero width joiner
        r'\U00002B50\U00002B55]+', '', text)
    # Remove markdown bold/italic markers
    text = re.sub(r'\*+', '', text)
    # Remove markdown headers
    text = re.sub(r'#+\s*', '', text)
    # Remove markdown links [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Remove URLs
    text = re.sub(r'https?://\S+', '', text)
    # Collapse extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


async def synthesize(text: str) -> bytes:
    """Convert text to speech audio (MP3 bytes).

    Uses edge-tts (online) with pyttsx3 (offline) as fallback.
    """
    text = _clean_for_speech(text)
    if not text:
        return b""
    try:
        return await _edge_tts(text)
    except Exception:
        if config.TTS_FALLBACK_OFFLINE:
            return await _pyttsx3_fallback(text)
        raise


async def _edge_tts(text: str) -> bytes:
    """Synthesize speech using edge-tts (Microsoft Edge online TTS)."""
    import edge_tts

    lang = _detect_language(text)
    voice = config.TTS_VOICE_ZH if lang == "zh" else config.TTS_VOICE_EN

    communicate = edge_tts.Communicate(text, voice)
    audio_chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])

    return b"".join(audio_chunks)


async def _pyttsx3_fallback(text: str) -> bytes:
    """Offline TTS using pyttsx3 — saves to a temp file and reads back."""
    import tempfile
    import pyttsx3

    loop = asyncio.get_event_loop()

    def _speak():
        engine = pyttsx3.init()
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()
        engine.save_to_file(text, tmp.name)
        engine.runAndWait()
        with open(tmp.name, "rb") as f:
            return f.read()

    return await loop.run_in_executor(None, _speak)

from __future__ import annotations

import requests
from typing import Dict

from pipeline.errors import VoicevoxError
from pipeline.logging_utils import get_logger

# Reuse existing low-level client for audio_query construction
from apis.voicevox import create_audio_query as _create_audio_query_low

log = get_logger(__name__)


def create_audio_query(text: str, speaker_id: int, host: str = "127.0.0.1", port: int = 50021,
                       pre_length: float = 0.0, post_length: float = 0.0) -> Dict:
    """Create VOICEVOX audio query or raise VoicevoxError.

    Mirrors apis.voicevox.create_audio_query but ensures typed return and clear error.
    """
    log.debug("voicevox.create_audio_query start", extra={
        "text_len": len(text), "speaker_id": speaker_id, "host": host, "port": port
    })
    result = _create_audio_query_low(text=text, speaker_id=speaker_id, host=host, port=port,
                                     pre_length=pre_length, post_length=post_length)
    if result is None:
        raise VoicevoxError(f"Failed to create audio_query (speaker_id={speaker_id})")
    return result


def synthesize_speech(audio_query: Dict, speaker_id: int, host: str = "127.0.0.1", port: int = 50021) -> bytes:
    """Call VOICEVOX /synthesis endpoint and return WAV bytes or raise VoicevoxError."""
    try:
        url = f"http://{host}:{port}/synthesis"
        params = {"speaker": speaker_id}
        headers = {"Content-Type": "application/json"}
        log.debug("voicevox.synthesis POST", extra={"url": url, "speaker_id": speaker_id})
        resp = requests.post(url, params=params, headers=headers, json=audio_query)
        resp.raise_for_status()
        return resp.content
    except requests.exceptions.RequestException as e:
        log.error("voicevox.synthesis failed", extra={"speaker_id": speaker_id, "error": str(e)})
        raise VoicevoxError(f"VOICEVOX synthesis failed (speaker_id={speaker_id}): {e}")


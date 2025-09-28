from __future__ import annotations

import json
import os
import re
import wave
from typing import Dict, List, Tuple

from pipeline.errors import AudioSynthesisError, VoicevoxError
from pipeline.logging_utils import get_logger
from pipeline.voicevox_client import create_audio_query as vv_create_query, synthesize_speech

log = get_logger(__name__)


def extract_scene_text(scene_data: Dict) -> Tuple[str, List[str]]:
    """Extract and concatenate text for a scene.

    Returns tuple of (full_text, list_of_parts)
    """
    parts: List[str] = []
    title = scene_data.get("title", "")
    if isinstance(title, str) and title.strip():
        parts.append(title.strip() + ",")
    contents = scene_data.get("contents") or []
    if isinstance(contents, list):
        for c in contents:
            for t in c.get("texts", []) or []:
                parts.append(str(t).strip())
        if parts:
            parts[-1] += "."
    return ("".join(parts), parts)


def combine_wav_files(input_files: List[str], output_file: str, silence_duration: float = 0.5) -> bool:
    """Combine multiple WAV files inserting silence between them."""
    if not input_files:
        log.warning("combine_wav_files: no inputs")
        return False
    try:
        with wave.open(input_files[0], 'rb') as first_wav:
            params = first_wav.getparams()
            sample_rate = params.framerate
            sample_width = params.sampwidth
            channels = params.nchannels

        silence_frames = int(sample_rate * silence_duration)
        silence_data = b'\x00' * (silence_frames * sample_width * channels)

        with wave.open(output_file, 'wb') as output_wav:
            output_wav.setparams(params)
            for i, input_file in enumerate(input_files):
                if not os.path.exists(input_file):
                    log.warning("combine_wav_files: missing file", extra={"file": input_file})
                    continue
                with wave.open(input_file, 'rb') as iw:
                    output_wav.writeframes(iw.readframes(iw.getnframes()))
                if i < len(input_files) - 1:
                    output_wav.writeframes(silence_data)
        log.info("combined WAV created", extra={"output": output_file, "count": len(input_files)})
        return True
    except Exception as e:
        log.exception("combine_wav_files failed")
        raise AudioSynthesisError(str(e))


def _natural_sort_key(filepath: str) -> int:
    basename = os.path.basename(os.path.dirname(filepath))
    nums = re.findall(r"\d+", basename)
    return int(nums[0]) if nums else 0


def generate_scene_voices(
    json_path: str,
    output_dir: str,
    speaker_id: int = 13,
    speed_scale: float = 1.2,
    host: str = "127.0.0.1",
    port: int = 50021,
    combine_audio: bool = True,
    silence_duration: float = 0.5,
) -> bool:
    """Generate voice WAV per scene and optionally combine all, writing timing artifacts.

    Writes per-scene:
      - script.txt, voice_query.json, scene_sub.json, voice_audio.wav
    Optionally writes combined_all_scenes.wav at output_dir root.
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    log.info("start voice generation", extra={
        "json_path": json_path, "output_dir": output_dir, "speaker_id": speaker_id,
        "speed_scale": speed_scale, "combine_audio": combine_audio
    })

    os.makedirs(output_dir, exist_ok=True)
    generated: List[str] = []

    for scene_key, scene_data in data.items():
        log.info("process scene", extra={"scene": scene_key})
        scene_text, text_all = extract_scene_text(scene_data)
        if not scene_text.strip():
            log.warning("empty scene text; skip", extra={"scene": scene_key})
            continue

        scene_out = os.path.join(output_dir, scene_key)
        os.makedirs(scene_out, exist_ok=True)

        with open(os.path.join(scene_out, "script.txt"), 'w', encoding='utf-8') as f:
            f.write(scene_text)

        # Build base audio query for whole scene
        audio_query = vv_create_query(text=scene_text, speaker_id=speaker_id, host=host, port=port,
                                        pre_length=0.0, post_length=0.0)

        audio_query["speedScale"] = speed_scale
        audio_query["prePhonemeLength"] = 0.0
        audio_query["postPhonemeLength"] = 0.0

        with open(os.path.join(scene_out, "voice_query.json"), 'w', encoding='utf-8') as f:
            json.dump(audio_query, f, ensure_ascii=False, indent=2)

        # Enrich kana for title + per text chunk to construct scene_sub.json
        kana_all: List[str] = []
        for txt in text_all:
            q = vv_create_query(text=txt, speaker_id=speaker_id, host=host, port=port)
            kana_text = ""
            for acc in q.get("accent_phrases", []) or []:
                for mora in acc.get("moras", []) or []:
                    kana_text += str(mora.get("text", ""))
            kana_all.append(kana_text)

        # Save scene_sub.json enriched
        if kana_all:
            scene_data["title_kana"] = kana_all[0]
            idx = 1
            for content in scene_data.get("contents", []) or []:
                texts = content.get("texts", []) or []
                content["texts_kana"] = kana_all[idx: idx + len(texts)]
                idx += len(texts)
        with open(os.path.join(scene_out, "scene_sub.json"), 'w', encoding='utf-8') as f:
            json.dump(scene_data, f, ensure_ascii=False, indent=2)

        wav_bytes = synthesize_speech(audio_query=audio_query, speaker_id=speaker_id, host=host, port=port)
        with open(os.path.join(scene_out, "voice_audio.wav"), 'wb') as f:
            f.write(wav_bytes)
        generated.append(os.path.join(scene_out, "voice_audio.wav"))

    log.info("voice generation done", extra={"scenes": len(generated)})

    if combine_audio and len(generated) > 1:
        combined = os.path.join(output_dir, "combined_all_scenes.wav")
        generated_sorted = sorted(generated, key=_natural_sort_key)
        ok = combine_wav_files(generated_sorted, combined, silence_duration)
        if ok:
            log.info("combined audio created", extra={"file": combined, "count": len(generated_sorted)})
        else:
            log.warning("combined audio failed")
        return ok
    return True


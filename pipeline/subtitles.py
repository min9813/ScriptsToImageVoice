from __future__ import annotations

import glob
import json
import os
import re
from typing import Dict, List, Tuple

from pipeline.errors import SubtitleGenerationError
from pipeline.logging_utils import get_logger
from pipeline.types import SubtitleSegment

log = get_logger(__name__)


def extract_segments_from_scene(scene_data: Dict) -> List[Dict]:
    segments: List[Dict] = []
    title_kana = scene_data.get("title_kana", "").strip() if isinstance(scene_data.get("title_kana"), str) else ""
    if title_kana:
        segments.append({
            "text": (scene_data.get("title") or "").strip(),
            "kana_text": title_kana,
            "type": "title-kana",
        })
    for content in (scene_data.get("contents") or []):
        if "texts_kana" in content:
            kana_list = content.get("texts_kana") or []
            texts_list = content.get("texts") or []
            for i, kana in enumerate(kana_list):
                if isinstance(kana, str) and kana.strip():
                    text_val = texts_list[i] if i < len(texts_list) else ""
                    segments.append({
                        "text": str(text_val).strip(),
                        "kana_text": kana.strip(),
                        "type": "kana",
                    })
    return segments


def analyze_voice_query_timing(query_file: str, segments: List[Dict]) -> List[SubtitleSegment]:
    try:
        with open(query_file, 'r', encoding='utf-8') as f:
            query_data = json.load(f)
    except Exception as e:
        raise SubtitleGenerationError(f"Failed to read voice_query.json: {e}")

    accent_phrases = query_data.get("accent_phrases", [])
    speed_scale = query_data.get("speedScale", 1.0) or 1.0

    combined_text = ""
    seg_positions: List[Dict] = []
    for seg in segments:
        kana = seg["kana_text"]
        start_pos = len(combined_text)
        combined_text += kana
        end_pos = len(combined_text)
        seg_positions.append({
            "segment": seg,
            "start_pos": start_pos,
            "end_pos": end_pos,
            "start_chars": kana[:3],
            "end_chars": kana[-3:],
        })

    char_times: List[Dict] = []
    cur_time = 0.0
    cur_pos = 0

    for phrase in accent_phrases:
        for mora in (phrase.get("moras") or []):
            ch = mora.get("text")
            if ch is None:
                continue
            consonant_length = (mora.get("consonant_length") or 0.0) / speed_scale
            vowel_length = (mora.get("vowel_length") or 0.0) / speed_scale
            dur = consonant_length + vowel_length
            if ch in ["pau", "cl", "N", "U", "I"]:
                cur_time += dur
                continue
            char_times.append({
                "char": ch,
                "char_pos": cur_pos,
                "start_time": cur_time,
                "end_time": cur_time + dur,
            })
            cur_time += dur
            cur_pos += len(ch)
        pause = phrase["pause_mora"]
        if pause:
            pause_vowel = pause.get("vowel_length") or 0.0
            pause_consonant = pause.get("consonant_length") or 0.0
            cur_time += (pause_vowel + pause_consonant) / 1.1

    result: List[SubtitleSegment] = []
    for i, sp in enumerate(seg_positions):
        start_pos = sp["start_pos"]
        end_pos = sp["end_pos"]
        seg = sp["segment"]

        start_time = 0.0
        for j, ct in enumerate(char_times):
            if ct["char_pos"] >= start_pos:
                start_time = ct["start_time"]
                ch_len = len(ct["char"])
                assert ct["char"] == sp["start_chars"][:ch_len]
                break

        end_time = cur_time
        for j in range(len(char_times) - 1, -1, -1):
            ct = char_times[j]
            if ct["char_pos"] < end_pos:
                end_time = ct["end_time"]
                ch_len = len(ct["char"])
                assert ct["char"] == sp["end_chars"][-ch_len:]
                break

        adj_start = start_time
        adj_end = end_time

        text_val = seg["text"]
        if text_val.endswith(".") and not text_val.endswith(".."):
            text_val = text_val[:-1]
        if text_val.endswith(",") and not text_val.endswith(",,"):
            text_val = text_val[:-1]

        result.append(SubtitleSegment(
            index=i + 1,
            start_time=adj_start,
            end_time=adj_end,
            text=text_val,
            kana_text=seg["kana_text"],
            segment_type=seg.get("type", "text"),
        ))

    print("="*30)
    print(result)
    print("="*30)


    return result


def _natural_sort_key(path: str) -> int:
    nums = re.findall(r"\d+", os.path.basename(path))
    return int(nums[0]) if nums else 0


def generate_combined_subtitles(base_dir: str, output_filename: str = "combined_subtitles.srt",
                                silence_duration: float = 0.5) -> tuple[bool, str]:
    scene_dirs = glob.glob(os.path.join(base_dir, "scene_*"))
    scene_files: List[tuple[str, str, Dict]] = []
    for scene_dir in sorted(scene_dirs, key=_natural_sort_key):
        scene_key = os.path.basename(scene_dir)
        query_file = os.path.join(scene_dir, "voice_query.json")
        scene_sub_json_file = os.path.join(scene_dir, "scene_sub.json")
        if not (os.path.exists(query_file) and os.path.exists(scene_sub_json_file)):
            log.warning("missing artifacts for scene", extra={"scene": scene_key})
            continue
        with open(scene_sub_json_file, 'r', encoding='utf-8') as f:
            scene_sub_data = json.load(f)
        scene_files.append((scene_key, query_file, scene_sub_data))

    if not scene_files:
        log.error(f"no scenes found for subtitles in {base_dir}", extra={"scene_files": scene_files})
        return False, ""

    all_segments: List[SubtitleSegment] = []
    current_time_offset = 0.0

    for scene_key, query_file, scene_sub_data in scene_files:
        segments = extract_segments_from_scene(scene_sub_data)
        if not segments:
            log.warning("no segments", extra={"scene": scene_key})
            continue
        try:
            scene_segments = analyze_voice_query_timing(query_file, segments)
        except AssertionError as e:
            log.error("timing assertion failed", extra={"scene": scene_key, "error": str(e)})
            continue
        except SubtitleGenerationError as e:
            log.error("subtitle generation failed", extra={"scene": scene_key, "error": str(e)})
            continue

        for seg in scene_segments:
            seg.start_time += current_time_offset
            seg.end_time += current_time_offset
            seg.index = len(all_segments) + 1
            all_segments.append(seg)

        if scene_segments:
            scene_duration = scene_segments[-1].end_time
            current_time_offset = scene_duration + silence_duration

        print("="*30)
        print(scene_segments)
        print("="*30)

    if not all_segments:
        log.error("no subtitle segments produced")
        return False, ""

    for i in range(len(all_segments) - 1):
        if all_segments[i].end_time < all_segments[i + 1].start_time:
            all_segments[i].end_time = all_segments[i + 1].start_time

    output_path = os.path.join(base_dir, output_filename)
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            for seg in all_segments:
                f.write(seg.to_srt_format())
        log.info("SRT generated", extra={"file": output_path, "segments": len(all_segments)})
        return True, output_path
    except Exception as e:
        log.error("SRT write failed", extra={"file": output_path, "error": str(e)})
        return False, ""

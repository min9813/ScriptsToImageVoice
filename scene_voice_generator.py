from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
from typing import List, Tuple

from pipeline.audio import generate_scene_voices
from pipeline.logging_utils import setup_logging, get_logger
from scene_subtitle_generator import generate_combined_subtitles

log = get_logger(__name__)


def _summarize_sub_json(json_path: str) -> Tuple[int, List[str]]:
    """Return scene count and a few scene keys for display."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return len(data), list(data.keys())[:5]


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を解析する"""
    parser = argparse.ArgumentParser(description="JSONファイルからVOICEVOX APIで音声合成を行うツール")
    parser.add_argument("--json_path", type=str, required=True, help="入力JSONファイルのパス")
    parser.add_argument("--output_dir", type=str, required=True, help="出力ディレクトリ")
    parser.add_argument("--speaker_id", type=int, default=13, help="スピーカーID (デフォルト: 13)")
    parser.add_argument("--speed_scale", type=float, default=1.15, help="音声の速度スケール (デフォルト: 1.15)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="VOICEVOXサーバーのホスト")
    parser.add_argument("--port", type=int, default=50021, help="VOICEVOXサーバーのポート")
    parser.add_argument("--summary", action='store_true', help="JSONファイルの内容を要約表示のみ")
    parser.add_argument("--combine_audio", action='store_true', default=True, help="全シーンの音声を結合する (デフォルト: True)")
    parser.add_argument("--no_combine", action='store_true', help="音声結合を無効にする")
    parser.add_argument("--silence_duration", type=float, default=0.5, help="シーン間の無音時間（秒）")
    parser.add_argument("--output_srt_filename", type=str, default="combined_subtitles.srt",
                        help="出力SRTファイル名 (デフォルト: combined_subtitles.srt)")
    parser.add_argument("--skip_voice_generation", action='store_true', help="音声生成をスキップする")
    parser.add_argument("--log_level", type=str, default=None, help="ログレベル (e.g., INFO, DEBUG)")
    return parser.parse_args()


def main() -> None:
    """
    メイン関数
    # 基本使用（結合音声も生成）
    python3 scene_voice_generator.py \
    --json_path sub.json \
    --output_dir output_directory

    # 音声結合を無効にして個別音声のみ生成
    python3 scene_voice_generator.py \
    --json_path sub.json \
    --output_dir output_directory \
    --no_combine

    # シーン間の無音時間を調整
    python3 scene_voice_generator.py \
    --json_path sub.json \
    --output_dir output_directory \
    --silence_duration 1.0
    """
    args = parse_args()
    setup_logging(args.log_level)

    if args.summary:
        try:
            count, keys = _summarize_sub_json(args.json_path)
            log.info("JSON summary", extra={"scenes": count, "first_keys": keys})
        except Exception as e:
            log.error("summary failed", extra={"error": str(e)})
        return

    combine_audio = args.combine_audio and not args.no_combine

    if not args.skip_voice_generation:
        ok = generate_scene_voices(
            json_path=args.json_path,
            output_dir=args.output_dir,
            speaker_id=args.speaker_id,
            speed_scale=args.speed_scale,
            host=args.host,
            port=args.port,
            combine_audio=combine_audio,
            silence_duration=args.silence_duration,
        )
        if not ok:
            log.error("音声生成に失敗しました")
            return

    ok, srt_path = generate_combined_subtitles(
        base_dir=args.output_dir,
        output_filename=args.output_srt_filename,
        silence_duration=args.silence_duration,
    )
    if not ok:
        log.error("字幕生成に失敗しました")
        return
    log.info("字幕生成完了", extra={"file": args.output_srt_filename})

    # Mirror original behavior: copy output_dir to edit/ next to sub.json
    target_dir = os.path.dirname(args.json_path)
    edit_dir = os.path.join(target_dir, "edit")
    log.info("copy dir to edit/", extra={"src": args.output_dir, "dst": edit_dir})
    os.makedirs(edit_dir, exist_ok=True)
    shutil.copytree(args.output_dir, edit_dir, dirs_exist_ok=True)

if __name__ == "__main__":
    main() 

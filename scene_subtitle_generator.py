from __future__ import annotations

import argparse
import logging

from pipeline.logging_utils import setup_logging, get_logger
from pipeline.subtitles import generate_combined_subtitles

log = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for subtitle generation."""
    parser = argparse.ArgumentParser(description="sub.jsonとvoice_query.jsonから字幕SRTファイルを生成する")
    parser.add_argument("--base_dir", type=str, required=True, help="scene_*ディレクトリを含むベースディレクトリ")
    parser.add_argument("--output_filename", type=str, default="combined_subtitles.srt",
                        help="出力SRTファイル名 (デフォルト: combined_subtitles.srt)")
    parser.add_argument("--silence_duration", type=float, default=0.5,
                        help="シーン間の無音時間（秒）(デフォルト: 0.5)")
    parser.add_argument("--log_level", type=str, default=None, help="ログレベル (e.g., INFO, DEBUG)")
    return parser.parse_args()


def main() -> None:
    """CLI entry point for generating combined subtitles.

    Examples:
      python3 scene_subtitle_generator.py --base_dir scene_outputs/20250916_2
      python3 scene_subtitle_generator.py --base_dir scene_outputs/20250916_2 --output_filename my_subtitles.srt
    """
    args = parse_args()
    setup_logging(args.log_level)
    log.info("subtitle generation start", extra={
        "base_dir": args.base_dir, "output": args.output_filename, "silence": args.silence_duration
    })

    ok, out = generate_combined_subtitles(
        base_dir=args.base_dir,
        output_filename=args.output_filename,
        silence_duration=args.silence_duration,
    )
    if ok:
        log.info("字幕生成が正常に完了しました！", extra={"file": out})
    else:
        log.error("字幕生成に失敗しました。")


if __name__ == "__main__":
    main()

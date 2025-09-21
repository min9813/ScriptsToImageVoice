import json
import os
import argparse
from typing import List, Dict, Optional
import glob
import re

from apis.voicevox import create_audio_query


class SubtitleSegment:
    """字幕セグメントを表すクラス"""
    
    def __init__(self, index: int, start_time: float, end_time: float, 
                 text: str, kana_text: str, segment_type: str = "text"):
        self.index = index
        self.start_time = start_time
        self.end_time = end_time
        self.text = text
        self.kana_text = kana_text
        self.segment_type = segment_type
    
    def to_srt_format(self) -> str:
        """SRT形式の文字列に変換する"""
        start_time_str = self._format_time(self.start_time)
        end_time_str = self._format_time(self.end_time)
        return f"{self.index}\n{start_time_str} --> {end_time_str}\n{self.text}\n"
    
    def _format_time(self, seconds: float) -> str:
        """秒をSRT時間形式に変換する"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds_int = int(seconds % 60)
        milliseconds = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds_int:02d},{milliseconds:03d}"


def extract_segments_from_scene(scene_data: Dict) -> List[Dict]:
    """
    シーンデータから各セグメント（title, texts）を抽出する
    
    Args:
        scene_data (Dict): シーンデータ
        
    Returns:
        List[Dict]: セグメント情報のリスト
    """
    segments = []
    
    # タイトルを追加
    if "title_kana" in scene_data and scene_data["title_kana"].strip():
        segments.append({
            "text": scene_data["title"].strip(),
            "kana_text": scene_data["title_kana"].strip(),
            "type": "title-kana"
        })
    
    # コンテンツのテキストを追加
    if "contents" in scene_data and isinstance(scene_data["contents"], list):
        for content_item in scene_data["contents"]:
            if "texts_kana" in content_item:
                for text_index, text_item in enumerate(content_item["texts_kana"]):
                    text = content_item["texts"][text_index]
                    if text_item.strip():
                        segments.append({
                            "text": text.strip(),
                            "kana_text": text_item.strip(),
                            "type": "kana"
                        })
    
    return segments


def analyze_voice_query_timing(query_file: str, 
                               segments: List[Dict]) -> List[SubtitleSegment]:
    """
    voice_query.jsonから各セグメントの時間を計算する
    
    Args:
        query_file (str): voice_query.jsonファイルのパス
        segments (List[Dict]): セグメント情報
        
    Returns:
        List[SubtitleSegment]: 時間付きセグメント
    """
    try:
        with open(query_file, 'r', encoding='utf-8') as f:
            query_data = json.load(f)
    except Exception as e:
        print(f"query.jsonファイルの読み込みに失敗: {e}")
        return []
    
    accent_phrases = query_data.get("accent_phrases", [])
    speed_scale = query_data.get("speedScale", 1.0)
    
    # 結合されたテキストを作成（スペース挿入ルール適用）
    combined_text = ""
    segment_positions = []  # 各セグメントの文字位置を記録
    
    for i, segment in enumerate(segments):
        kana_text = segment["kana_text"]
        # 現在の文字位置を記録
        start_pos = len(combined_text)
        
        # テキストを追加
        combined_text += kana_text
        end_pos = len(combined_text)
        
        segment_positions.append({
            "segment": segment,
            "start_pos": start_pos,
            "end_pos": end_pos,
            "start_chars": kana_text[:3],
            "end_chars": kana_text[-3:]
        })
        
        # # 最後のセグメント以外にスペースを追加
        # if i < len(segments) - 1:
        #     combined_text += " "
    
    # 文字ごとの時間マッピングを作成
    char_times = []
    current_time = 0.0
    current_char_pos = 0
    
    for phrase in accent_phrases:
        if "moras" in phrase:
            for index, mora in enumerate(phrase["moras"]):
                if "text" not in mora:
                    continue


                
                char = mora["text"]
                # if char == "ジョ" and phrase["moras"][index + 1]["text"] == "セ" and phrase["moras"][index + 2]["text"] == "エ" and phrase["moras"][index + 3]["text"] == "ノ":
                #     print("current_time:", current_time)
                #     lksdfa
                consonant_length = mora.get("consonant_length", 0.0) or 0.0
                vowel_length = mora.get("vowel_length", 0.0) or 0.0
                char_duration = consonant_length + vowel_length
                
                # 特殊な音素は文字位置を進めない
                if char in ["pau", "cl", "N", "U", "I"]:
                    current_time += char_duration
                    continue
                
                char_times.append({
                    "char": char,
                    "char_pos": current_char_pos,
                    "start_time": current_time,
                    "end_time": current_time + char_duration
                })
                
                current_time += char_duration
                current_char_pos += len(char)
        
        # pause_moraを処理
        # 文字の長さには segments は入っていない（自動生成されるため）
        # 長さだけ加算する
        if "pause_mora" in phrase and phrase["pause_mora"]:
            pause_mora = phrase["pause_mora"]
            # if "text" in pause_mora and pause_mora["text"] in ["、", "。"]:
            #     char_times.append({
            #         "char": pause_mora["text"],
            #         "char_pos": current_char_pos,
            #         "start_time": current_time,
            #         "end_time": current_time
            #     })
            #     current_char_pos += 1
            
            vowel_length = pause_mora.get("vowel_length", 0.0) or 0.0
            current_time += vowel_length
    
    # セグメントごとの時間を計算
    subtitle_segments = []
    
    for i, seg_pos in enumerate(segment_positions):
        target_segment_start_pos = seg_pos["start_pos"]
        target_segment_end_pos = seg_pos["end_pos"]
        segment = seg_pos["segment"]
        
        # 開始時間を見つける
        start_time = 0.0
        for j, char_time in enumerate(char_times):
            if char_time["char_pos"] >= target_segment_start_pos:
                start_time = char_time["start_time"]
                char_len = len(char_time["char"])
                assert char_time["char"] == seg_pos["start_chars"][:char_len], f"{char_time['char']} != {seg_pos['start_chars']}, seg_pos:{seg_pos}, char_time:{char_time} prev:{char_times[:j+1]}"
                break
        
        # 終了時間を見つける
        end_time = current_time
        for j in range(len(char_times) - 1, -1, -1):
            char_time = char_times[j]
            if char_time["char_pos"] < target_segment_end_pos:
                end_time = char_time["end_time"]
                char_len = len(char_time["char"])
                assert char_time["char"] == seg_pos["end_chars"][-char_len:], f"{char_time['char']} != {seg_pos['end_chars']}, seg_pos:{seg_pos}, char_time:{char_time} prev:{char_times[:j]}"
                break
        
        # speedScaleを考慮して時間を調整
        adjusted_start_time = start_time / speed_scale
        adjusted_end_time = end_time / speed_scale

        input_text = segment["text"]
        if input_text.endswith(".") and not input_text.endswith(".."):
            input_text = input_text[:-1]

        if input_text.endswith(",") and not input_text.endswith(",,"):
            input_text = input_text[:-1]

        subtitle_segments.append(SubtitleSegment(
            index=i + 1,
            start_time=adjusted_start_time,
            end_time=adjusted_end_time,
            text=input_text,
            kana_text=segment["kana_text"],
            segment_type=segment["type"]
        ))

    # if "ダイヨンイ" in segment_positions[0]["segment"]["kana_text"]:
    #     print(subtitle_segments[0].to_srt_format())
    #     print(subtitle_segments[1].to_srt_format())
    #     print(subtitle_segments[2].to_srt_format())
    #     sdfa
    
    return subtitle_segments


def natural_sort_key(path: str) -> int:
    """ファイルパスから数字を抽出してソート用のキーを生成"""
    numbers = re.findall(r'\d+', os.path.basename(path))
    return int(numbers[0]) if numbers else 0


def generate_combined_subtitles(base_dir: str, 
                                output_filename: str = "combined_subtitles.srt",
                                silence_duration: float = 0.5) -> bool:
    """
    複数のシーンのvoice_query.jsonから結合された字幕を生成する
    
    Args:
        base_dir (str): scene_*ディレクトリを含むベースディレクトリ
        output_filename (str): 出力SRTファイル名
        silence_duration (float): シーン間の無音時間（秒）
        
    Returns:
        bool: 成功した場合True
    """
    # sub.jsonファイルを読み込み
    # sub_json_path = os.path.join(base_dir, "sub.json")
    # if not os.path.exists(sub_json_path):
    #     # 親ディレクトリを探す
    #     parent_dir = os.path.dirname(base_dir)
    #     sub_json_path = os.path.join(parent_dir, "sub.json")
    #     if not os.path.exists(sub_json_path):
    #         print(f"sub.jsonファイルが見つかりません: {base_dir}")
    #         return False
    
    # try:
    #     with open(sub_json_path, 'r', encoding='utf-8') as f:
    #         sub_data = json.load(f)
    # except Exception as e:
    #     print(f"sub.jsonの読み込みに失敗: {e}")
    #     return False
    
    # scene_*ディレクトリからvoice_query.jsonファイルを見つける
    scene_dirs = glob.glob(os.path.join(base_dir, "scene_*"))
    scene_files = []
    for scene_dir in sorted(scene_dirs):
        scene_key = os.path.basename(scene_dir)
        query_file = os.path.join(scene_dir, "voice_query.json")
        scene_sub_json_file = os.path.join(scene_dir, "scene_sub.json")
        with open(scene_sub_json_file, 'r', encoding='utf-8') as f:
            scene_sub_data = json.load(f)
        if os.path.exists(query_file):
            scene_files.append((scene_key, query_file, scene_sub_data))
        else:
            print(f"警告: {query_file} が見つかりません")
    
    if not scene_files:
        print(f"voice_query.jsonファイルが見つかりません: {base_dir}")
        return False
    
    print(f"見つかったシーン数: {len(scene_files)}")
    
    # 全セグメントを時間オフセット付きで収集
    all_segments = []
    current_time_offset = 0.0
    
    for scene_key, query_file, scene_sub_data in scene_files:
        print(f"処理中: {scene_key}")
        
        # シーンからセグメントを抽出
        segments = extract_segments_from_scene(scene_sub_data)
        
        if not segments:
            print(f"  警告: {scene_key} にセグメントが見つかりません")
            continue
        
        # セグメントの時間を計算
        scene_segments = analyze_voice_query_timing(query_file, segments)
        
        if not scene_segments:
            print(f"  警告: {scene_key} の時間計算に失敗")
            continue
        
        # 時間オフセットを適用
        for segment in scene_segments:
            segment.start_time += current_time_offset
            segment.end_time += current_time_offset
            segment.index = len(all_segments) + 1  # 連番に変更
            all_segments.append(segment)

        
        # 次のシーンのためのオフセットを更新
        if scene_segments:
            scene_duration = scene_segments[-1].end_time - current_time_offset
            # silence_durationも考慮（speedScaleは各シーンで既に適用済み）
            current_time_offset += scene_duration + silence_duration
        
        print(f"  セグメント数: {len(scene_segments)}")
    
    if not all_segments:
        print("字幕セグメントが見つかりませんでした")
        return False

    # 次のsegment のstart_time まで拡張
    for segment_index, segment in enumerate(all_segments[:-1]):
        next_segment = all_segments[segment_index + 1]
        if segment.end_time < next_segment.start_time:
            segment.end_time = next_segment.start_time
    
    # SRTファイルを出力
    output_path = os.path.join(base_dir, output_filename)
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            for segment in all_segments:
                f.write(segment.to_srt_format())
                f.write("\n")
        
        print(f"\n=== SRT生成完了 ===")
        print(f"出力ファイル: {output_path}")
        print(f"総字幕数: {len(all_segments)}")
        
        if all_segments:
            total_duration = all_segments[-1].end_time
            print(f"総再生時間: {total_duration:.2f}秒")
        
        return True, output_path
        
    except Exception as e:
        print(f"SRTファイルの書き込みに失敗: {e}")
        return False, ""


def parse_args():
    """
    コマンドライン引数を解析する
    
    Returns:
        argparse.Namespace: 解析された引数
    """
    parser = argparse.ArgumentParser(
        description="sub.jsonとvoice_query.jsonから字幕SRTファイルを生成する"
    )
    parser.add_argument("--base_dir", type=str, required=True,
                        help="scene_*ディレクトリを含むベースディレクトリ")
    parser.add_argument("--output_filename", type=str, 
                        default="combined_subtitles.srt",
                        help="出力SRTファイル名 (デフォルト: combined_subtitles.srt)")
    parser.add_argument("--silence_duration", type=float, default=0.5,
                        help="シーン間の無音時間（秒）(デフォルト: 0.5)")
    
    return parser.parse_args()


def main():
    """
    メイン関数
    
    使用例:
    python3 scene_subtitle_generator.py --base_dir scene_outputs/20250916_2
    python3 scene_subtitle_generator.py --base_dir scene_outputs/20250916_2 --output_filename my_subtitles.srt
    """
    args = parse_args()
    
    success = generate_combined_subtitles(
        base_dir=args.base_dir,
        output_filename=args.output_filename,
        silence_duration=args.silence_duration
    )
    
    if success:
        print("\n字幕生成が正常に完了しました！")
    else:
        print("\n字幕生成に失敗しました。")


if __name__ == "__main__":
    main() 
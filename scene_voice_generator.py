import requests
import json
import os
import argparse
import wave
import shutil
from typing import Dict, Optional, List

from apis.voicevox import create_audio_query
from scene_subtitle_generator import generate_combined_subtitles


def synthesize_speech(audio_query: Dict, speaker_id: int, 
                      host: str = "127.0.0.1", 
                      port: int = 50021) -> Optional[bytes]:
    """
    音声クエリから音声を合成する
    
    Args:
        audio_query (Dict): 音声クエリ
        speaker_id (int): スピーカーID
        host (str): VOICEVOXサーバーのホスト
        port (int): VOICEVOXサーバーのポート
        
    Returns:
        Optional[bytes]: 音声データ（WAVファイル）。エラー時はNone
    """
    try:
        url = f"http://{host}:{port}/synthesis"
        params = {"speaker": speaker_id}
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, params=params, headers=headers,
                                 json=audio_query)
        response.raise_for_status()
        return response.content
    except requests.exceptions.RequestException as e:
        print(f"音声合成に失敗しました (speaker_id={speaker_id}): {e}")
        return None


def extract_scene_text(scene_data: Dict) -> str:
    """
    シーンデータからテキストを抽出して結合する
    
    Args:
        scene_data (Dict): シーンデータ
        
    Returns:
        str: 結合されたテキスト
    """
    
    # 通常のシーン形式の場合
    text_all = []
    
    # タイトルを追加
    if "title" in scene_data and scene_data["title"].strip():
        text_all.append(scene_data["title"].strip()+",")
    
    # コンテンツのテキストを追加
    if "contents" in scene_data and isinstance(scene_data["contents"], list):
        for content_item in scene_data["contents"]:
            texts = content_item["texts"]
            for text in texts:
                text_all.append(text.strip())
        text_all[-1] += "."

    
    return "".join(text_all), text_all


def combine_wav_files(input_files: List[str], output_file: str,
                      silence_duration: float = 0.5) -> bool:
    """
    複数のWAVファイルを結合する
    
    Args:
        input_files (List[str]): 入力WAVファイルのパスリスト
        output_file (str): 出力WAVファイルのパス
        silence_duration (float): ファイル間の無音時間（秒）
        
    Returns:
        bool: 成功した場合True
    """
    if not input_files:
        print("結合するファイルがありません")
        return False
    
    try:
        # 最初のファイルでフォーマットを取得
        with wave.open(input_files[0], 'rb') as first_wav:
            params = first_wav.getparams()
            sample_rate = params.framerate
            sample_width = params.sampwidth
            channels = params.nchannels
        
        # 無音データを生成
        silence_frames = int(sample_rate * silence_duration)
        silence_data = b'\x00' * (silence_frames * sample_width * channels)
        
        # 出力ファイルを作成
        with wave.open(output_file, 'wb') as output_wav:
            output_wav.setparams(params)
            
            for i, input_file in enumerate(input_files):
                if not os.path.exists(input_file):
                    print(f"警告: ファイルが見つかりません: {input_file}")
                    continue
                
                print(f"結合中: {os.path.basename(input_file)}")
                
                # 音声データを読み込み
                with wave.open(input_file, 'rb') as input_wav:
                    audio_data = input_wav.readframes(input_wav.getnframes())
                    output_wav.writeframes(audio_data)
                
                # 最後のファイル以外は無音を挿入
                if i < len(input_files) - 1:
                    output_wav.writeframes(silence_data)
        
        print(f"結合完了: {output_file}")
        return True
        
    except Exception as e:
        print(f"ファイル結合エラー: {e}")
        return False


def generate_scene_voices(json_path: str, output_dir: str,
                          speaker_id: int = 13,
                          speed_scale: float = 1.2,
                          host: str = "127.0.0.1",
                          port: int = 50021,
                          combine_audio: bool = True,
                          silence_duration: float = 0.5) -> bool:
    """
    JSONファイルからシーンごとに音声を生成する
    
    Args:
        json_path (str): 入力JSONファイルのパス
        output_dir (str): 出力ディレクトリ
        speaker_id (int): スピーカーID
        speed_scale (float): 音声の速度スケール
        host (str): VOICEVOXサーバーのホスト
        port (int): VOICEVOXサーバーのポート
        combine_audio (bool): 全シーンの音声を結合するかどうか
        silence_duration (float): シーン間の無音時間（秒）
    """
    # JSONファイルを読み込み
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"JSONファイルが見つかりません: {json_path}")
        return False
    except json.JSONDecodeError as e:
        print(f"JSONファイルの解析に失敗しました: {e}")
        return False
    except Exception as e:
        print(f"JSONファイルの読み込みに失敗しました: {e}")
        return False
    
    print(f"JSONファイルを読み込みました: {json_path}")
    print(f"出力ディレクトリ: {output_dir}")
    print(f"スピーカーID: {speaker_id}")
    print(f"速度スケール: {speed_scale}")
    print(f"音声結合: {'有効' if combine_audio else '無効'}")
    
    # 生成された音声ファイルのパスを記録
    generated_audio_files = []
    
    # 各シーンを処理
    for scene_key, scene_data in data.items():
        print(f"\n=== {scene_key} の処理開始 ===")
        
        # シーンテキストを抽出
        scene_text, text_all = extract_scene_text(scene_data)
        
        if not scene_text.strip():
            print(f"警告: {scene_key} のテキストが空です。スキップします。")
            continue
        
        print(f"テキスト: {scene_text[:100]}...")
        
        # 出力ディレクトリを作成
        scene_output_dir = os.path.join(output_dir, scene_key)
        os.makedirs(scene_output_dir, exist_ok=True)
        
        # テキストファイルを保存
        text_filename = os.path.join(scene_output_dir, "script.txt")
        with open(text_filename, 'w', encoding='utf-8') as f:
            f.write(scene_text)
        
        # 音声クエリを作成
        print("音声クエリを作成中...")
        audio_query = create_audio_query(text=scene_text,
                                         speaker_id=speaker_id,
                                         host=host, port=port)
        if audio_query is None:
            print(f"エラー: {scene_key} の音声クエリ作成に失敗しました")
            continue

        audio_query["prePhonemeLength"] = 0.0
        audio_query["postPhonemeLength"] = 0.0

        # 速度スケールを適用
        audio_query["speedScale"] = speed_scale
        
        # クエリをJSONファイルとして保存
        query_filename = os.path.join(scene_output_dir, "voice_query.json")
        with open(query_filename, 'w', encoding='utf-8') as f:
            json.dump(audio_query, f, ensure_ascii=False, indent=2)



        # カナ読み取得のために各テキストに対して音声クエリを作成
        each_text_audio_queries = []
        for text in text_all:
            each_audio_query = create_audio_query(text=text,
                                             speaker_id=speaker_id,
                                             host=host, port=port)
            if each_audio_query is None:
                print(f"エラー: {scene_key} の音声クエリ作成に失敗しました")
                continue
            accent_phrases = each_audio_query["accent_phrases"]
            kana_text = ""
            for accent_phrase in accent_phrases:
                moras = accent_phrase["moras"]
                for mora in moras:
                    kana_text += mora["text"]

            each_text_audio_queries.append(kana_text)


        

        # scene sub.json を保存
        sub_filename = os.path.join(scene_output_dir, "scene_sub.json")
        scene_data["title_kana"] = each_text_audio_queries[0]
        # print(len(each_text_audio_queries))
        each_text_audio_queries = each_text_audio_queries[1:]
        current_offset_index = 0
        for each_content in scene_data["contents"]:
            each_content["texts_kana"] = []
            # print(len(each_content["texts"]), current_offset_index)
            for index, text in enumerate(each_content["texts"]):
                each_content["texts_kana"].append(each_text_audio_queries[index + current_offset_index])
            current_offset_index += len(each_content["texts"])
        with open(sub_filename, 'w', encoding='utf-8') as f:
            json.dump(scene_data, f, ensure_ascii=False, indent=2)
        
        # 音声を合成
        print("音声を合成中...")
        audio_data = synthesize_speech(audio_query=audio_query,
                                       speaker_id=speaker_id,
                                       host=host, port=port)
        if audio_data is None:
            print(f"エラー: {scene_key} の音声合成に失敗しました")
            continue
        
        # 音声データをWAVファイルとして保存
        audio_filename = os.path.join(scene_output_dir, "voice_audio.wav")
        with open(audio_filename, 'wb') as f:
            f.write(audio_data)
        
        print(f"{scene_key} の処理完了:")
        print(f"  - スクリプト: {text_filename}")
        print(f"  - クエリ: {query_filename}")
        print(f"  - 音声: {audio_filename}")
        
        # 生成された音声ファイルを記録
        generated_audio_files.append(audio_filename)
    
    print("\n全てのシーンの音声生成が完了しました！")
    
    # 音声結合が有効で、複数のファイルがある場合
    if combine_audio and len(generated_audio_files) > 1:
        print("\n音声ファイルを結合中...")
        combined_filename = os.path.join(output_dir, "combined_all_scenes.wav")
        
        # 自然順序でソート（scene0, scene1, scene2, ...の順番）
        def natural_sort_key(filepath):
            basename = os.path.basename(os.path.dirname(filepath))
            # scene_keyから数字部分を抽出してソート
            import re
            numbers = re.findall(r'\d+', basename)
            return int(numbers[0]) if numbers else 0
        
        sorted_files = sorted(generated_audio_files, key=natural_sort_key)
        
        success = combine_wav_files(sorted_files, combined_filename, silence_duration)
        
        if success:
            print(f"\n=== 結合完了 ===")
            print(f"結合ファイル: {combined_filename}")
            print(f"結合されたシーン数: {len(sorted_files)}")
            
            # 結合されたファイルの情報を表示
            try:
                with wave.open(combined_filename, 'rb') as wav_file:
                    frames = wav_file.getnframes()
                    sample_rate = wav_file.getframerate()
                    duration = frames / sample_rate
                    print(f"総再生時間: {duration:.2f}秒")
            except Exception as e:
                print(f"音声情報の取得に失敗: {e}")
        else:
            print("音声結合に失敗しました")
    elif combine_audio and len(generated_audio_files) == 1:
        print("\nシーンが1つのため、結合はスキップされました")
    elif not combine_audio:
        print("\n音声結合は無効に設定されています")
    
    print(f"\n出力ディレクトリ: {output_dir}")
    return True


def get_scene_summary(json_path: str) -> None:
    """
    JSONファイルのシーン情報を要約表示する
    
    Args:
        json_path (str): 入力JSONファイルのパス
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"JSONファイルの読み込みに失敗しました: {e}")
        return
    
    print(f"JSONファイル: {json_path}")
    print(f"シーン数: {len(data)}")
    print("\nシーン一覧:")
    
    for scene_key, scene_data in data.items():
        scene_text = extract_scene_text(scene_data)
        print(f"  {scene_key}: {scene_text[:50]}...")


def parse_args():
    """
    コマンドライン引数を解析する
    
    Returns:
        argparse.Namespace: 解析された引数
    """
    parser = argparse.ArgumentParser(
        description="JSONファイルからVOICEVOX APIで音声合成を行うツール"
    )
    parser.add_argument("--json_path", type=str, required=True,
                        help="入力JSONファイルのパス")
    parser.add_argument("--output_dir", type=str, required=True,
                        help="出力ディレクトリ")
    parser.add_argument("--speaker_id", type=int, default=13,
                        help="スピーカーID (デフォルト: 13)")
    parser.add_argument("--speed_scale", type=float, default=1.15,
                        help="音声の速度スケール (デフォルト: 1.15)")
    parser.add_argument("--host", type=str, default="127.0.0.1",
                        help="VOICEVOXサーバーのホスト")
    parser.add_argument("--port", type=int, default=50021,
                        help="VOICEVOXサーバーのポート")
    parser.add_argument("--summary", action='store_true',
                        help="JSONファイルの内容を要約表示のみ")
    parser.add_argument("--combine_audio", action='store_true',
                        default=True,
                        help="全シーンの音声を結合する (デフォルト: True)")
    parser.add_argument("--no_combine", action='store_true',
                        help="音声結合を無効にする")
    parser.add_argument("--silence_duration", type=float, default=0.5,
                        help="シーン間の無音時間（秒）")
    parser.add_argument("--output_srt_filename", type=str, default="combined_subtitles.srt",
                        help="出力SRTファイル名 (デフォルト: combined_subtitles.srt)")
    parser.add_argument("--skip_voice_generation", action='store_true',
                        help="音声生成をスキップする")
    return parser.parse_args()


def main():
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
    
    if args.summary:
        # 要約表示のみ
        get_scene_summary(args.json_path)
    else:
        # 音声結合の設定
        combine_audio = args.combine_audio and not args.no_combine
        
        # 音声生成を実行
        if not args.skip_voice_generation:
            success = generate_scene_voices(json_path=args.json_path,
                                output_dir=args.output_dir,
                                speaker_id=args.speaker_id,
                                speed_scale=args.speed_scale,
                                host=args.host,
                                port=args.port,
                                combine_audio=combine_audio,
                                silence_duration=args.silence_duration)
            if not success:
                print("音声生成に失敗しました")
                return

        success, output_path = generate_combined_subtitles(
            base_dir=args.output_dir,
            output_filename=args.output_srt_filename,
            silence_duration=args.silence_duration
        )
        if not success:
            print("字幕生成に失敗しました")
            return

        print(f"字幕生成完了: {args.output_srt_filename}")

        target_dir = os.path.dirname(args.json_path)
        edit_dir = os.path.join(target_dir, "edit")
        print(f"copy dir to edit dir. {args.output_dir} --> {edit_dir}")
        os.makedirs(edit_dir, exist_ok=True)
        shutil.copytree(args.output_dir, edit_dir, dirs_exist_ok=True)

if __name__ == "__main__":
    main() 
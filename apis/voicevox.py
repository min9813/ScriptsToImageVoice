import requests
from typing import Optional, Dict


def create_audio_query(text: str, speaker_id: int, 
                       host: str = "127.0.0.1", 
                       port: int = 50021,
                       pre_length: float = 0.0,
                       post_length: float = 0.0) -> Optional[Dict]:
    """
    テキストから音声クエリを作成する
    
    Args:
        text (str): 音声合成するテキスト
        speaker_id (int): スピーカーID
        host (str): VOICEVOXサーバーのホスト
        port (int): VOICEVOXサーバーのポート
        
    Returns:
        Optional[Dict]: 音声クエリ。エラー時はNone
    """
    try:
        url = f"http://{host}:{port}/audio_query"
        params = {
            "text": text,
            "speaker": speaker_id,
            "prePhonemeLength": pre_length,   # 各音素の前の無音
            "postPhonemeLength": post_length
        }
        response = requests.post(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"音声クエリの作成に失敗しました "
              f"(speaker_id={speaker_id}): {e}")
        return None
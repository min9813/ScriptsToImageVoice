#!/usr/bin/env python3
"""
Image Prompt Extractor

sub.jsonファイルからすべてのimage_promptを抽出し、
プロジェクトディレクトリにprompts.jsonとして保存するスクリプト
"""

import json
import argparse
from pathlib import Path
from typing import Any


class ImagePromptExtractor:
    """
    JSONファイルからimage_promptを抽出し、整理して保存するクラス
    
    SOLID原則に従い、単一責任原則でプロンプト抽出に特化
    """
    
    def __init__(
        self, 
        base_path: str = "/Users/min9813/project/tiktok/voicevox"
    ):
        """
        Image Prompt Extractorを初期化
        
        Args:
            base_path: プロジェクトのベースパス
        """
        self.base_path = Path(base_path)
        self.t_sozai_path = self.base_path / "t_sozai" / "upload_movies"
        self.projects_path = (
            self.base_path / "chatgpt-playwright" / "projects"
        )
    
    def extract_prompts_from_scene(
        self, scene_data: dict[str, Any]
    ) -> list[str]:
        """
        シーンデータからすべてのimage_promptを抽出
        
        Args:
            scene_data: シーンのJSONデータ
            
        Returns:
            抽出されたプロンプトのリスト
        """
        prompts = []
        
        # シーンレベルのimage_prompt
        if "image_prompt" in scene_data:
            prompts.append(scene_data["image_prompt"])
        
        # contentsレベルのimage_prompt
        if "contents" in scene_data:
            for content in scene_data["contents"]:
                if "image_prompt" in content:
                    # "いつもの"など不完全なプロンプトをフィルタリング
                    prompt = content["image_prompt"]
                    if len(prompt) > 10:  # 最小文字数でフィルタ
                        prompts.append(prompt)
        
        return prompts
    
    def extract_all_prompts(self, sub_json_data: dict[str, Any]) -> list[str]:
        """
        sub.jsonから全てのimage_promptを抽出
        
        Args:
            sub_json_data: sub.jsonの全データ
            
        Returns:
            すべてのプロンプトのリスト
        """
        all_prompts = []
        
        for scene_key, scene_data in sub_json_data.items():
            if scene_key.startswith("scene_"):
                prompts = self.extract_prompts_from_scene(scene_data)
                all_prompts.extend(prompts)
        
        return all_prompts
    
    def load_sub_json(self, directory_name: str) -> dict[str, Any]:
        """
        指定されたディレクトリからsub.jsonを読み込み
        
        Args:
            directory_name: ディレクトリ名（例: "20250921"）
            
        Returns:
            sub.jsonのデータ
            
        Raises:
            FileNotFoundError: sub.jsonが見つからない場合
            json.JSONDecodeError: JSONの解析に失敗した場合
        """
        sub_json_path = self.t_sozai_path / directory_name / "sub.json"
        
        if not sub_json_path.exists():
            raise FileNotFoundError(f"sub.json not found: {sub_json_path}")
        
        with open(sub_json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def save_prompts_json(
        self, prompts: list[str], directory_name: str
    ) -> None:
        """
        プロンプトリストをprompts.jsonとして保存
        
        Args:
            prompts: プロンプトのリスト
            directory_name: プロジェクトディレクトリ名
        """
        # プロジェクトディレクトリを作成
        project_dir = self.projects_path / directory_name
        project_dir.mkdir(parents=True, exist_ok=True)
        
        # prompts.jsonとして保存
        prompts_file = project_dir / "prompts.json"
        
        with open(prompts_file, 'w', encoding='utf-8') as f:
            json.dump(prompts, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Saved {len(prompts)} prompts to: {prompts_file}")
    
    def process_directory(self, directory_name: str) -> None:
        """
        指定されたディレクトリのsub.jsonを処理してprompts.jsonを生成
        
        Args:
            directory_name: 処理するディレクトリ名
        """
        try:
            print(f"🔍 Processing directory: {directory_name}")
            
            # sub.jsonを読み込み
            sub_data = self.load_sub_json(directory_name)
            
            # プロンプトを抽出
            prompts = self.extract_all_prompts(sub_data)
            
            # 重複を除去（順序を保持）
            unique_prompts = []
            seen = set()
            for prompt in prompts:
                if prompt not in seen:
                    unique_prompts.append(prompt)
                    seen.add(prompt)
            
            print(f"📝 Extracted {len(unique_prompts)} unique prompts")
            
            # prompts.jsonとして保存
            self.save_prompts_json(unique_prompts, directory_name)
            
        except Exception as e:
            print(f"❌ Error processing {directory_name}: {e}")
            raise
    
    def list_available_directories(self) -> list[str]:
        """
        処理可能なディレクトリの一覧を取得
        
        Returns:
            ディレクトリ名のリスト
        """
        if not self.t_sozai_path.exists():
            return []
        
        directories = []
        for item in self.t_sozai_path.iterdir():
            if item.is_dir() and (item / "sub.json").exists():
                directories.append(item.name)
        
        return sorted(directories)


def main():
    """メイン実行関数"""
    parser = argparse.ArgumentParser(
        description="Extract image prompts from sub.json files"
    )
    parser.add_argument(
        "directory",
        nargs="?",
        help="Directory name to process (e.g., '20250921')"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available directories"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all available directories"
    )
    
    args = parser.parse_args()
    
    extractor = ImagePromptExtractor()
    
    if args.list:
        # 利用可能なディレクトリを表示
        directories = extractor.list_available_directories()
        print("📁 Available directories:")
        for directory in directories:
            print(f"  - {directory}")
        return
    
    if args.all:
        # すべてのディレクトリを処理
        directories = extractor.list_available_directories()
        print(f"🚀 Processing {len(directories)} directories...")
        
        for directory in directories:
            extractor.process_directory(directory)
        
        print("✨ All directories processed successfully!")
        return
    
    if args.directory:
        # 指定されたディレクトリを処理
        extractor.process_directory(args.directory)
    else:
        # デフォルトで20250921を処理
        extractor.process_directory("20250921")


if __name__ == "__main__":
    main()

import json
import os
from typing import Dict, Any

CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.json')

_config_cache: Dict[str, Any] | None = None

def load_config() -> Dict[str, Any]:
    """
    設定ファイル (config.json) を読み込み、辞書として返します。
    初回読み込み後はキャッシュされた値を返します。

    Returns:
        Dict[str, Any]: 設定ファイルの内容。

    Raises:
        FileNotFoundError: 設定ファイルが見つからない場合。
        json.JSONDecodeError: 設定ファイルのJSON形式が不正な場合。
    """
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    try:
        with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
            _config_cache = config
            return config
    except FileNotFoundError:
        print(f"エラー: 設定ファイルが見つかりません: {CONFIG_FILE_PATH}")
        raise
    except json.JSONDecodeError as e:
        print(f"エラー: 設定ファイルの形式が不正です: {CONFIG_FILE_PATH} - {e}")
        raise

def get_hpb_selectors() -> Dict[str, str]:
    """HPB関連のセレクタを取得します。"""
    config = load_config()
    return config.get('hpb_selectors', {})

def get_gbp_selectors() -> Dict[str, str]:
    """GBP関連のセレクタを取得します。"""
    config = load_config()
    return config.get('gbp_selectors', {})

def get_settings() -> Dict[str, Any]:
    """一般設定を取得します。"""
    config = load_config()
    return config.get('settings', {})

if __name__ == '__main__':
    # 簡単なテスト実行
    try:
        config = load_config()
        print("設定ファイルの読み込みに成功しました:")
        print(json.dumps(config, indent=2, ensure_ascii=False))

        hpb_selectors = get_hpb_selectors()
        print("\nHPB セレクタ:")
        print(hpb_selectors)

        gbp_selectors = get_gbp_selectors()
        print("\nGBP セレクタ:")
        print(gbp_selectors)

        settings = get_settings()
        print("\n一般設定:")
        print(settings)

    except Exception as e:
        print(f"テスト実行中にエラーが発生しました: {e}") 
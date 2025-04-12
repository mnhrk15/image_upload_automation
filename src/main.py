import sys
import json
from src.config_manager import load_config

def main():
    """アプリケーションのエントリーポイント"""
    print("アプリケーションを開始します...")
    try:
        config = load_config()
        print("設定ファイルを読み込みました:")
        print(json.dumps(config, indent=2, ensure_ascii=False))
        # ここに将来的にGUIの起動コードなどを追加
        print("\nアプリケーションの初期化が完了しました。(GUI未実装)")
    except Exception as e:
        print(f"アプリケーションの起動中にエラーが発生しました: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main() 
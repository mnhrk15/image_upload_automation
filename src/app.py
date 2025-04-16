import faulthandler
faulthandler.enable()

import sys
import os
import logging
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from src.main_window import MainWindow
from src.config_manager import load_config

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

def main():
    """アプリケーションのエントリーポイント"""
    try:
        logger.info("アプリケーションを起動中...")
        
        # 設定ファイルの読み込み
        config = load_config()
        logger.debug("設定ファイルの読み込みに成功しました")
        
        # 一時ディレクトリの確認
        temp_dir = os.path.join(os.path.dirname(__file__), '..', 'temp')
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            logger.debug(f"一時ディレクトリを作成しました: {temp_dir}")
        
        # PyQt6アプリケーションの初期化
        app = QApplication(sys.argv)
        app.setApplicationName("HotPepper Beauty 画像投稿ツール")
        app.setOrganizationName("HPB Image Uploader")
        
        # スタイルシートの設定（オプション）
        # with open('resources/style.qss', 'r') as f:
        #     app.setStyleSheet(f.read())
        
        # メインウィンドウの作成と表示
        main_window = MainWindow()
        main_window.show()
        
        logger.info("アプリケーションの初期化が完了しました")
        # アプリケーションの実行
        sys.exit(app.exec())
        
    except Exception as e:
        logger.error(f"アプリケーションの起動中にエラーが発生しました: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main() 
import unittest
import sys
import os
from unittest.mock import patch, MagicMock
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt

# src ディレクトリをパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.main_window import MainWindow

class TestMainWindow(unittest.TestCase):
    """メインウィンドウの基本機能をテストするクラス"""
    
    @classmethod
    def setUpClass(cls):
        # QApplicationのインスタンスは一度だけ作成
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])
    
    def setUp(self):
        # 各テスト前にメインウィンドウを初期化
        self.window = MainWindow()
    
    def test_initial_ui_state(self):
        """UIの初期状態をテスト"""
        # タイトルが正しく設定されているか
        self.assertEqual(self.window.windowTitle(), "HotPepper Beauty 画像投稿ツール")
        
        # 最小サイズが正しく設定されているか
        self.assertGreaterEqual(self.window.size().width(), 800)
        self.assertGreaterEqual(self.window.size().height(), 600)
        
        # 入力フィールドが空であるか
        self.assertEqual(self.window.hpb_url_input.text(), "")
        self.assertEqual(self.window.gbp_url_input.text(), "")
        
        # 取得ボタンが有効であるか
        self.assertTrue(self.window.fetch_button.isEnabled())
        
        # 投稿ボタンが無効であるか (初期状態では画像がないため)
        self.assertFalse(self.window.upload_button.isEnabled())
        
        # 全選択/全解除ボタンが無効であるか (初期状態では画像がないため)
        self.assertFalse(self.window.select_all_button.isEnabled())
        self.assertFalse(self.window.deselect_all_button.isEnabled())
    
    def test_empty_url_validation(self):
        """空のURL入力の検証テスト"""
        # モックのQMessageBoxを作成
        with patch('PyQt6.QtWidgets.QMessageBox.warning') as mock_warning:
            # 空のURLで画像取得ボタンをクリック
            self.window.fetch_images()
            
            # 警告ダイアログが表示されたか確認
            mock_warning.assert_called_once()
    
    @patch('src.main_window.Worker')
    def test_fetch_images_process(self, mock_worker):
        """画像取得プロセスのテスト"""
        # モックのWorkerを設定
        mock_worker_instance = MagicMock()
        mock_worker.return_value = mock_worker_instance
        
        # テスト用のURLを入力
        self.window.hpb_url_input.setText("https://beauty.hotpepper.jp/slnH000135046/")
        
        # 画像取得ボタンをクリック
        self.window.fetch_images()
        
        # ボタンが無効化されたか確認
        self.assertFalse(self.window.fetch_button.isEnabled())
        
        # Workerが正しく作成・開始されたか確認
        mock_worker.assert_called_once()
        self.assertTrue(mock_worker_instance.signals.result.connect.called)
        self.assertTrue(mock_worker_instance.signals.error.connect.called)
    
    def test_log_message(self):
        """ログメッセージ機能のテスト"""
        # 初期ログにはアプリケーション準備完了のメッセージが含まれているはず
        self.assertIn("アプリケーションの準備が完了しました", self.window.log_text.toPlainText())
        
        # テストメッセージをログに追加
        test_message = "テストメッセージ"
        self.window.log_message(test_message)
        
        # ログテキストにメッセージが含まれているか確認
        self.assertIn(test_message, self.window.log_text.toPlainText())
    
    def tearDown(self):
        # 各テスト後にウィンドウを閉じる
        self.window.close()

if __name__ == "__main__":
    unittest.main() 
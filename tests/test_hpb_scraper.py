import unittest
from unittest.mock import patch, Mock, MagicMock
import os
import sys
import shutil
import tempfile
import json
from io import BytesIO
from pathlib import Path

# src ディレクトリをパスに追加（絶対パスで指定）
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.hpb_scraper import (
    get_salon_name, 
    _get_style_page_info, 
    fetch_latest_style_images, 
    download_images,
    _get_cleaned_image_url
)


class TestHPBScraper(unittest.TestCase):
    
    def setUp(self):
        # テスト用の一時ディレクトリを作成
        self.temp_dir = tempfile.mkdtemp()
        
        # テスト用のHPB URL
        self.test_hpb_url = "https://beauty.hotpepper.jp/slnH000135046/"
        
        # テスト用のHTMLとレスポンスを準備
        with open(os.path.join(os.path.dirname(__file__), 'test_data', 'hpb_salon_page.html'), 'rb') as f:
            self.salon_page_html = f.read()
        
        with open(os.path.join(os.path.dirname(__file__), 'test_data', 'hpb_style_page.html'), 'rb') as f:
            self.style_page_html = f.read()
        
        # 一時的に config.json をモック
        self.orig_config = None
        if os.path.exists('config/config.json'):
            with open('config/config.json', 'r') as f:
                self.orig_config = json.load(f)
        
        self.test_config = {
            "hpb_selectors": {
                "salon_name": "#mainContents > div.detailHeader.cFix.pr > div > div.pL10.oh.hMin120 > div > p.detailTitle > a",
                "max_page_element": "#mainContents > div.mT20 > div.pH10.mT25.pr > p.pa.bottom0.right0",
                "style_image": "#jsiHoverAlphaLayerScope img.bdImgGray",
                "image_url_cleanup_pattern": "?impolicy="
            },
            "settings": {
                "max_images_to_fetch": 3,
                "download_delay_seconds": 0.01
            }
        }
        
        # テスト用の設定ファイルディレクトリを作成
        os.makedirs('config', exist_ok=True)
        with open('config/config.json', 'w') as f:
            json.dump(self.test_config, f)
    
    def tearDown(self):
        # テスト用の一時ディレクトリを削除
        shutil.rmtree(self.temp_dir)
        
        # 元の config.json を復元
        if self.orig_config:
            with open('config/config.json', 'w') as f:
                json.dump(self.orig_config, f)
    
    def _create_mock_response(self, content, status_code=200, url=''):
        mock_response = Mock()
        mock_response.content = content
        mock_response.status_code = status_code
        mock_response.raise_for_status = Mock()
        mock_response.url = url
        return mock_response
    
    def test_get_cleaned_image_url(self):
        """画像URLのクリーニング機能をテスト"""
        # テストケース1: クエリパラメータ付きURL
        test_url = "https://imgbp.hotp.jp/CSP/IMG_SRC/65/58/B185806558/B185806558.jpg?impolicy=HPB_policy_default&w=154&h=205"
        expected = "https://imgbp.hotp.jp/CSP/IMG_SRC/65/58/B185806558/B185806558.jpg"
        self.assertEqual(_get_cleaned_image_url(test_url, "?impolicy="), expected)
        
        # テストケース2: 不正なURL
        test_url = "data:image/png;base64,iVBORw0KGgoAA..."
        self.assertIsNone(_get_cleaned_image_url(test_url, "?impolicy="))
        
        # テストケース3: 完全なURL（変更なし）
        test_url = "https://imgbp.hotp.jp/CSP/IMG_SRC/65/58/B185806558/B185806558.jpg"
        self.assertEqual(_get_cleaned_image_url(test_url, "?impolicy="), test_url)
    
    @patch('src.hpb_scraper._make_request')
    def test_get_salon_name(self, mock_make_request):
        """サロン名取得機能をテスト"""
        # モックレスポンスを設定
        mock_make_request.return_value = self._create_mock_response(self.salon_page_html)
        
        # テスト実行
        salon_name = get_salon_name(self.test_hpb_url)
        
        # 検証
        self.assertIsNotNone(salon_name)
        self.assertEqual(salon_name, "ANGEL‐青葉台‐")
        mock_make_request.assert_called_once_with(self.test_hpb_url)
    
    @patch('src.hpb_scraper._make_request')
    def test_get_style_page_info(self, mock_make_request):
        """スタイルページ情報取得機能をテスト"""
        # モックレスポンスを設定
        mock_response = self._create_mock_response(self.style_page_html)
        mock_make_request.return_value = mock_response
        
        # テスト実行
        style_base_url, max_page = _get_style_page_info(self.test_hpb_url)
        
        # 検証
        self.assertEqual(style_base_url, "https://beauty.hotpepper.jp/slnH000135046/style/")
        self.assertEqual(max_page, 8)  # モックHTMLに「1/8ページ」とある想定
        mock_make_request.assert_called_once()
    
    @patch('src.hpb_scraper._make_request')
    @patch('src.hpb_scraper._get_style_page_info')
    def test_fetch_latest_style_images(self, mock_get_style_page_info, mock_make_request):
        """最新スタイル画像取得機能をテスト"""
        # スタイルページ情報のモック
        mock_get_style_page_info.return_value = ("https://beauty.hotpepper.jp/slnH000135046/style/", 2)
        
        # 画像URLが含まれるHTMLをモック
        mock_make_request.return_value = self._create_mock_response(self.style_page_html)
        
        # テスト実行
        image_urls = fetch_latest_style_images(self.test_hpb_url)
        
        # 検証
        self.assertIsInstance(image_urls, list)
        self.assertLessEqual(len(image_urls), 3)  # テスト設定で最大3枚
        mock_get_style_page_info.assert_called_once_with(self.test_hpb_url)
        self.assertGreaterEqual(mock_make_request.call_count, 1)  # 少なくとも1回は呼ばれている
    
    @patch('src.hpb_scraper._make_request')
    def test_download_images(self, mock_make_request):
        """画像ダウンロード機能をテスト"""
        # モック画像データ
        mock_image_data = BytesIO(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82').getvalue()
        
        # テスト用の画像URLとモックレスポンス
        image_urls = [
            "https://example.com/image1.jpg",
            "https://example.com/image2.png",
            "https://example.com/image3.jpg"
        ]
        mock_make_request.return_value = self._create_mock_response(mock_image_data)
        
        # テスト実行
        downloaded_paths = download_images(image_urls, self.temp_dir)
        
        # 検証
        self.assertEqual(len(downloaded_paths), 3)
        for path in downloaded_paths:
            self.assertTrue(os.path.exists(path))
            self.assertTrue(os.path.getsize(path) > 0)
        self.assertEqual(mock_make_request.call_count, 3)


if __name__ == '__main__':
    # テスト用データディレクトリの作成
    test_data_dir = os.path.join(os.path.dirname(__file__), 'test_data')
    os.makedirs(test_data_dir, exist_ok=True)
    
    # テスト用HTMLファイルが存在しない場合、サンプルHTMLを作成
    salon_page_path = os.path.join(test_data_dir, 'hpb_salon_page.html')
    if not os.path.exists(salon_page_path):
        with open(salon_page_path, 'wb') as f:
            # サロンページのサンプルHTML
            salon_html = '''
            <html>
                <body>
                    <div id="mainContents">
                        <div class="detailHeader cFix pr">
                            <div>
                                <div class="pL10 oh hMin120">
                                    <div>
                                        <p class="detailTitle">
                                            <a href="https://beauty.hotpepper.jp/slnH000135046/">ANGEL‐青葉台‐</a>
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </body>
            </html>
            '''.encode('utf-8')
            f.write(salon_html)
    
    style_page_path = os.path.join(test_data_dir, 'hpb_style_page.html')
    if not os.path.exists(style_page_path):
        with open(style_page_path, 'wb') as f:
            # スタイルページのサンプルHTML
            style_html = '''
            <html>
                <body>
                    <div id="mainContents">
                        <div class="mT20">
                            <div class="pH10 mT25 pr">
                                <p class="pa bottom0 right0">
                                    1/8ページ
                                    <a href="/slnH000135046/style/PN2.html" class="iS arrowPagingR">次へ</a>
                                </p>
                            </div>
                        </div>
                        <div id="jsiHoverAlphaLayerScope">
                            <img src="https://imgbp.hotp.jp/CSP/IMG_SRC/65/58/B185806558/B185806558.jpg?impolicy=HPB_policy_default&amp;w=154&amp;h=205" class="bdImgGray" alt="サンプル画像1">
                            <img src="https://imgbp.hotp.jp/CSP/IMG_SRC/65/59/B185806559/B185806559.jpg?impolicy=HPB_policy_default&amp;w=154&amp;h=205" class="bdImgGray" alt="サンプル画像2">
                            <img src="https://imgbp.hotp.jp/CSP/IMG_SRC/65/60/B185806560/B185806560.jpg?impolicy=HPB_policy_default&amp;w=154&amp;h=205" class="bdImgGray" alt="サンプル画像3">
                        </div>
                    </div>
                </body>
            </html>
            '''.encode('utf-8')
            f.write(style_html)
    
    unittest.main() 
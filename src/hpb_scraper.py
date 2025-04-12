import requests
from bs4 import BeautifulSoup
import os
import urllib.parse
import time
import logging
import re
from typing import List, Tuple, Optional, Dict, Any

from src.config_manager import get_hpb_selectors, get_settings

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 一時ディレクトリ (プロジェクトルートからの相対パスを想定)
TEMP_DIR = os.path.join(os.path.dirname(__file__), '..', 'temp')

# --- Helper Functions --- #

def _make_request(url: str, retries: int = 3, delay: float = 1.0) -> Optional[requests.Response]:
    """指定されたURLにリクエストを送信し、レスポンスを返す。リトライ機能付き。"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    for i in range(retries):
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status() # HTTPエラーがあれば例外発生
            return response
        except requests.exceptions.RequestException as e:
            logger.warning(f"リクエスト失敗 ({i+1}/{retries}): {url} - {e}")
            if i < retries - 1:
                time.sleep(delay)
    logger.error(f"リクエスト失敗: {url} (リトライ上限超過)")
    return None

def _get_cleaned_image_url(src: str, cleanup_pattern: str) -> Optional[str]:
    """画像のsrc属性からクリーンなURLを抽出する。"""
    if not src:
        return None
    # クエリパラメータを除去
    url_parts = urllib.parse.urlsplit(src)
    cleaned_url = urllib.parse.urlunsplit((url_parts.scheme, url_parts.netloc, url_parts.path, '', ''))
    # 特定のパターンを除去 (configで指定されたパターン)
    if cleanup_pattern and cleanup_pattern in cleaned_url:
        cleaned_url = cleaned_url.split(cleanup_pattern)[0]
    
    # 不完全なURLやデータURIなどをフィルタリング (簡単なチェック)
    if not cleaned_url.startswith(('http://', 'https://')) or ';base64,' in cleaned_url:
        logger.debug(f"無効な画像URLをスキップ: {src[:100]}")
        return None
    return cleaned_url

# --- Core Scraping Functions --- #

def get_salon_name(hpb_top_url: str) -> Optional[str]:
    """HPBトップページURLからサロン名を取得する。"""
    logger.info(f"サロン名を取得中: {hpb_top_url}")
    selectors = get_hpb_selectors()
    salon_name_selector = selectors.get('salon_name')
    if not salon_name_selector:
        logger.error("設定ファイルにサロン名セレクタ (salon_name) がありません。")
        return None

    response = _make_request(hpb_top_url)
    if not response:
        return None

    try:
        soup = BeautifulSoup(response.content, 'html.parser')
        salon_name_element = soup.select_one(salon_name_selector)
        if salon_name_element:
            salon_name = salon_name_element.text.strip()
            logger.info(f"サロン名取得成功: {salon_name}")
            return salon_name
        else:
            logger.error(f"サロン名要素が見つかりません。セレクタ: {salon_name_selector}")
            return None
    except Exception as e:
        logger.error(f"サロン名取得中にエラーが発生しました: {e}", exc_info=True)
        return None

def _get_style_page_info(hpb_top_url: str) -> Tuple[Optional[str], int]:
    """HPBトップページURLからスタイルページのベースURLと最大ページ数を取得する。"""
    logger.info(f"スタイルページ情報を取得中: {hpb_top_url}")
    # HPBのURL構造からスタイルページのベースURLを推測
    # 例: https://beauty.hotpepper.jp/slnH000xxxxxx/ -> https://beauty.hotpepper.jp/slnH000xxxxxx/style/
    if not hpb_top_url.endswith('/'):
        hpb_top_url += '/'
    style_base_url = urllib.parse.urljoin(hpb_top_url, 'style/')

    selectors = get_hpb_selectors()
    max_page_selector = selectors.get('max_page_element')
    if not max_page_selector:
        logger.warning("設定ファイルに最大ページ数要素セレクタ (max_page_element) がありません。ページ数を1と仮定します。")
        return style_base_url, 1

    logger.info(f"最初のスタイルページにアクセス中: {style_base_url}")
    response = _make_request(style_base_url)
    if not response:
        return style_base_url, 1 # エラー時は1ページと仮定

    max_page = 1
    try:
        soup = BeautifulSoup(response.content, 'html.parser')
        max_page_element = soup.select_one(max_page_selector)
        if max_page_element:
            # 例: "1/8ページ" から最大ページ数を抽出
            text = max_page_element.text.strip()
            logger.debug(f"ページネーション要素のテキスト: '{text}'")
            
            # パターン1: "1/8ページ" のような形式
            match = re.search(r'(\d+)/(\d+)ページ', text)
            if match:
                max_page = int(match.group(2)) # 2番目のキャプチャグループが最大ページ数
                logger.info(f"ページネーション形式1から最大ページ数を抽出: {max_page}")
            else:
                # パターン2: "全2ページ" のような形式 (念のため)
                match = re.search(r'全(\d+)ページ', text)
                if match:
                    max_page = int(match.group(1))
                    logger.info(f"ページネーション形式2から最大ページ数を抽出: {max_page}")
                else:
                    logger.warning(f"最大ページ数をテキストから抽出できませんでした: '{text}'。1ページと仮定します。")
        else:
            logger.warning(f"最大ページ数要素が見つかりません。セレクタ: {max_page_selector}。1ページと仮定します。")
    except Exception as e:
        logger.error(f"最大ページ数取得中にエラー: {e}", exc_info=True)
        # エラー発生時も1ページとみなす

    logger.info(f"スタイルベースURL: {style_base_url}, 最大ページ数: {max_page}")
    return style_base_url, max_page

def fetch_latest_style_images(hpb_top_url: str) -> List[str]:
    """
    指定されたHPBトップURLから最新のスタイル画像URLを取得する。
    最大10件 (設定ファイルで変更可能) のユニークな高解像度URLを返す。
    """
    logger.info(f"最新スタイル画像の取得を開始: {hpb_top_url}")
    selectors = get_hpb_selectors()
    settings = get_settings()
    image_selector = selectors.get('style_image')
    cleanup_pattern = selectors.get('image_url_cleanup_pattern', '')
    max_images = settings.get('max_images_to_fetch', 10)
    delay_seconds = settings.get('download_delay_seconds', 0.5)

    if not image_selector:
        logger.error("設定ファイルにスタイル画像セレクタ (style_image) がありません。")
        return []

    style_base_url, max_page = _get_style_page_info(hpb_top_url)
    if not style_base_url:
        return []

    unique_image_urls = set()
    fetched_urls_list = []

    # 最終ページから遡って処理
    for page_num in range(max_page, 0, -1):
        if len(unique_image_urls) >= max_images:
            break

        # ページURLの形式は「PN」大文字を使用
        if page_num == 1:
            # 1ページ目はページ番号なしのベースURL
            page_url = style_base_url
        else:
            # 2ページ目以降は「PN2.html」などの形式
            page_url = f"{style_base_url}PN{page_num}.html"
        
        logger.info(f"スタイルページを処理中: {page_url} ({len(unique_image_urls)}/{max_images} 枚取得済み)")

        response = _make_request(page_url)
        if not response:
            continue # エラーなら次のページへ

        try:
            soup = BeautifulSoup(response.content, 'html.parser')
            img_elements = soup.select(image_selector)
            logger.debug(f"ページ {page_num}: {len(img_elements)} 個の画像要素を発見")

            if not img_elements:
                logger.warning(f"ページ {page_num} で画像要素が見つかりません。セレクタ: {image_selector}")
                # 構造変化の可能性がある。もしくは最終ページに要素がないケースも？
                # 最初のページでなければ警告のみで継続
                if page_num != 1:
                    continue
                else:
                    # 1ページ目でも見つからない場合は明確に失敗
                    logger.error("スタイル画像が1枚も見つかりませんでした。サイト構造の変更またはセレクタの問題の可能性があります。")
                    return []

            # ページ内の画像を逆順（新しい順）に処理
            for img in reversed(img_elements):
                src = img.get('src')
                cleaned_url = _get_cleaned_image_url(src, cleanup_pattern)

                if cleaned_url and cleaned_url not in unique_image_urls:
                    unique_image_urls.add(cleaned_url)
                    fetched_urls_list.append(cleaned_url)
                    logger.debug(f"新規画像URLを追加: {cleaned_url} ({len(unique_image_urls)}/{max_images})")
                    if len(unique_image_urls) >= max_images:
                        break # 最大数に達したら内部ループも抜ける

        except Exception as e:
            logger.error(f"ページ {page_url} の解析中にエラー: {e}", exc_info=True)
            # エラーが発生しても、次のページの処理を試みる

        # 次のページへのリクエスト前に少し待機
        if len(unique_image_urls) < max_images and page_num > 1:
            time.sleep(delay_seconds)

    logger.info(f"合計 {len(fetched_urls_list)} 件のユニークな画像URLを取得しました。")
    return fetched_urls_list

def download_images(image_urls: List[str], temp_dir: str = TEMP_DIR) -> List[str]:
    """画像URLのリストから画像をダウンロードし、保存先のパスリストを返す。"""
    logger.info(f"{len(image_urls)} 件の画像をダウンロード中...")
    downloaded_paths = []

    if not os.path.exists(temp_dir):
        try:
            os.makedirs(temp_dir)
            logger.info(f"一時ディレクトリを作成しました: {temp_dir}")
        except OSError as e:
            logger.error(f"一時ディレクトリの作成に失敗しました: {temp_dir} - {e}")
            return []

    for i, url in enumerate(image_urls):
        try:
            response = _make_request(url)
            if response and response.content:
                # ファイル名を生成 (例: image_001.jpg)
                file_extension = os.path.splitext(urllib.parse.urlparse(url).path)[1] or '.jpg' # 拡張子がなければ.jpg
                # 拡張子にクエリパラメータなどが含まれる場合があるため、基本的なものに限定
                if file_extension.lower() not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                    file_extension = '.jpg' # 不明な場合はjpgとする
                
                filename = f"image_{i+1:03d}{file_extension}"
                filepath = os.path.join(temp_dir, filename)

                with open(filepath, 'wb') as f:
                    f.write(response.content)
                logger.info(f"画像を保存しました ({i+1}/{len(image_urls)}): {filepath} (from {url})")
                downloaded_paths.append(filepath)
            else:
                logger.warning(f"画像のダウンロードに失敗しました (空のレスポンス): {url}")

            # ダウンロードの間にも少し待機 (サーバー負荷軽減)
            settings = get_settings()
            delay = settings.get('download_delay_seconds', 0.5)
            time.sleep(delay / 2) # リクエスト間隔より少し短く

        except Exception as e:
            logger.error(f"画像のダウンロード/保存中にエラー: {url} - {e}", exc_info=True)

    logger.info(f"合計 {len(downloaded_paths)} 件の画像をダウンロードしました。")
    return downloaded_paths


# --- Main Execution for Testing --- #
if __name__ == '__main__':
    # テスト用のHPB URL (実際の美容室URL)
    test_hpb_url = "https://beauty.hotpepper.jp/slnH000135046/" # エンジェル 青葉台（ANGEL）

    print(f"--- サロン名取得テスト ({test_hpb_url}) ---")
    salon_name = get_salon_name(test_hpb_url)
    if salon_name:
        print(f"取得したサロン名: {salon_name}")
    else:
        print("サロン名の取得に失敗しました。")

    print(f"\n--- 最新スタイル画像URL取得テスト ({test_hpb_url}) ---")
    latest_image_urls = fetch_latest_style_images(test_hpb_url)
    if latest_image_urls:
        print(f"{len(latest_image_urls)} 件の画像URLを取得しました:")
        for i, url in enumerate(latest_image_urls):
            print(f"  {i+1}: {url}")
        
        print(f"\n--- 画像ダウンロードテスト ---")
        downloaded_files = download_images(latest_image_urls)
        if downloaded_files:
            print(f"{len(downloaded_files)} 件の画像を {TEMP_DIR} にダウンロードしました:")
            for file_path in downloaded_files:
                print(f"  - {os.path.basename(file_path)}")
        else:
            print("画像のダウンロードに失敗しました。")

    else:
        print("スタイル画像URLの取得に失敗しました。")

    print("\n--- テスト完了 --- (セレクタが正しくないと失敗します)") 
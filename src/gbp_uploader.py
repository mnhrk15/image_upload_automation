import os
import sys
import time
import logging
import asyncio
from typing import List, Dict, Optional, Any
from pathlib import Path

from playwright.async_api import async_playwright, Browser, Page, BrowserContext, TimeoutError

from src.config_manager import get_gbp_selectors, get_settings

# ロギング設定
logger = logging.getLogger(__name__)

class PlaywrightManager:
    """Playwrightブラウザの管理を行うクラス"""
    
    def __init__(self, browser_type='chromium'):
        self.playwright = None
        self.browser = None
        self.context = None
        self.settings = get_settings()
        self.storage_state_path = self._get_storage_state_path()
        self.headless = self.settings.get('headless', False)
        self.browser_type = browser_type  # 'chromium' または 'firefox'
    
    def _get_storage_state_path(self) -> str:
        """storage_state ファイルのパスを取得"""
        path = self.settings.get('storage_state_path', 'storage_state.json')
        if not os.path.isabs(path):
            # 絶対パスでない場合は、プロジェクトルートからの相対パスと見なす
            path = os.path.join(os.path.dirname(__file__), '..', path)
        return path
    
    async def start(self) -> BrowserContext:
        """Playwrightブラウザを起動し、BrowserContextを返す"""
        logger.info(f"{self.browser_type}ブラウザを起動中...")
        self.playwright = await async_playwright().start()
        
        # ブラウザの起動オプションを設定
        browser_options = {
            'headless': self.headless,
            'args': [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-infobars',
                '--window-size=1920,1080'
            ]
        }
        
        # ブラウザタイプに応じてブラウザを起動
        if self.browser_type == 'firefox':
            self.browser = await self.playwright.firefox.launch(headless=self.headless)
        else:  # デフォルトはchromium
            self.browser = await self.playwright.chromium.launch(**browser_options)
        
        # コンテキストオプションの設定
        context_options = {
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'viewport': {'width': 1920, 'height': 1080},
            'screen': {'width': 1920, 'height': 1080},
            'device_scale_factor': 1.0,
            'is_mobile': False,
            'has_touch': False,
            'locale': 'ja-JP'
        }
        if os.path.exists(self.storage_state_path):
            logger.info(f"既存のstorage_stateを読み込み中: {self.storage_state_path}")
            context_options['storage_state'] = self.storage_state_path
        
        self.context = await self.browser.new_context(**context_options)
        
        # JavaScriptを実行してwebdriverプロパティを削除
        if self.browser_type == 'chromium':
            await self.context.add_init_script("""
            () => {
                // WebDriverの特性を削除
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // Chrome特有のオートメーション検出特性を削除
                if (window.chrome) {
                    delete window.chrome.csi;
                    delete window.chrome.runtime;
                }
                
                // ユーザーエージェントに一般的でないプラグインを追加
                const originalAppendChild = document.head.appendChild.bind(document.head);
                document.head.appendChild = function(node) {
                    if (node.nodeName === 'SCRIPT' && node.src.includes('recaptcha')) {
                        return originalAppendChild(node);
                    }
                    return originalAppendChild(node);
                };
            }
            """)
        
        return self.context
    
    async def save_storage_state(self):
        """現在のstorage_stateを保存"""
        if self.context:
            logger.info(f"storage_stateを保存: {self.storage_state_path}")
            await self.context.storage_state(path=self.storage_state_path)
        else:
            logger.warning("コンテキストが初期化されていないため、storage_stateを保存できません")
    
    async def close(self):
        """ブラウザとPlaywrightを終了"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info(f"{self.browser_type}ブラウザを終了しました")
    
    def is_storage_state_available(self) -> bool:
        """storage_stateファイルが存在するかチェック"""
        return os.path.exists(self.storage_state_path)


class GoogleAuthManager:
    """Google認証を管理するクラス"""
    
    def __init__(self, context: BrowserContext):
        self.context = context
    
    async def is_logged_in(self) -> bool:
        """Googleにログインしているかチェック"""
        logger.info("ログイン状態を確認中...")
        
        try:
            page = await self.context.new_page()
            await page.goto("https://accounts.google.com/signin/v2/identifier")
            
            # リダイレクト後のURLをチェック
            current_url = page.url
            logger.debug(f"現在のURL: {current_url}")
            
            # ログイン済みの場合は myaccount.google.com などに
            # リダイレクトされている可能性がある
            is_logged_in = "myaccount.google.com" in current_url or "accounts.google.com/o/oauth2" in current_url
            
            await page.close()
            
            if is_logged_in:
                logger.info("Googleにログイン済みです")
            else:
                logger.info("Googleにログインしていません")
            
            return is_logged_in
            
        except Exception as e:
            logger.error(f"ログイン状態の確認中にエラーが発生しました: {e}", exc_info=True)
            return False
    
    async def login(self, progress_callback=None) -> bool:
        """Google アカウントにログイン（マニュアル）"""
        logger.info("Google ログインページを開きます")
        
        if progress_callback:
            progress_callback("Googleログインページを開いています...")
        
        try:
            page = await self.context.new_page()
            
            # Googleログインページにアクセス
            await page.goto("https://accounts.google.com/signin/v2", timeout=30000)
            
            if progress_callback:
                progress_callback("ログインを完了してください（手動操作）...")
            
            # ユーザーに対して手動でログインを促すメッセージ
            logger.info("手動でログインしてください。ログイン完了後、自動的に次のステップに進みます。")
            
            # ログイン成功の判定方法を複数用意して、いずれかが検出されるまで待機
            success = False
            timeout = 5 * 60 * 1000  # 5分間のタイムアウト
            
            try:
                # 以下のURLパターンのいずれかへのリダイレクトを待機
                login_success_patterns = [
                    "**/myaccount.google.com/**",
                    "**/accounts.google.com/signin/signinchooser**",
                    "**/accounts.google.com/ManageAccount**",
                    "**/google.com/**",
                    "**/www.google.com/**",
                    "**/mail.google.com/**"
                ]
                
                # いずれかのパターンに一致するまで待機
                logger.info("ログイン完了を待機中...")
                
                # タイムアウトを5分に設定
                start_time = time.time()
                timeout_seconds = 300  # 5分
                
                while time.time() - start_time < timeout_seconds:
                    # ページが閉じられたかチェック
                    if page.is_closed():
                        logger.info("ページが閉じられました。ログイン状態を再確認します。")
                        success = await self.is_logged_in()
                        break
                        
                    # 現在のURLをチェック
                    current_url = page.url
                    
                    # URLパターンのいずれかにマッチするか確認
                    for pattern in login_success_patterns:
                        if self._url_matches_pattern(current_url, pattern.replace("**", "")):
                            logger.info(f"ログイン成功URLパターンを検出: {current_url}")
                            success = True
                            break
                    
                    if success:
                        break
                    
                    # ページが移動していないか確認
                    if "accounts.google.com/signin" not in current_url:
                        logger.info(f"ログインページから移動を検出: {current_url}")
                        # 新しいURLに移動したが、成功パターンには一致しなかった場合
                        # 様子を見るために少し長めに待機してから再確認
                        await asyncio.sleep(3)
                        success = await self.is_logged_in()
                        break
                    
                    # 1秒待機して再チェック
                    await asyncio.sleep(1)
                
                # タイムアウトした場合
                if not success and time.time() - start_time >= timeout_seconds:
                    logger.warning("ログイン待機がタイムアウトしました")
                    
            except Exception as e:
                logger.error(f"ログイン待機中にエラーが発生: {e}")
                # ページが閉じられた場合などにここに到達する可能性がある
                # その場合はログイン状態を直接チェック
                try:
                    success = await self.is_logged_in()
                    logger.info(f"直接のログイン状態チェック結果: {success}")
                except Exception as inner_e:
                    logger.error(f"ログイン状態の直接チェック中にエラー: {inner_e}")
            
            # ページを閉じる
            try:
                if not page.is_closed():
                    await page.close()
            except Exception as e:
                logger.error(f"ページを閉じる際にエラー: {e}")
            
            if success:
                logger.info("Googleログインが完了しました")
                if progress_callback:
                    progress_callback("Googleログインが完了しました")
                return True
            else:
                logger.warning("Googleログインが完了したか確認できませんでした")
                if progress_callback:
                    progress_callback("ログイン状態を再確認しています...")
                
                # 最終確認として再度ログイン状態をチェック
                final_check = await self.is_logged_in()
                if final_check:
                    logger.info("最終確認: ログイン済みです")
                    if progress_callback:
                        progress_callback("ログイン確認: ログイン済みです")
                    return True
                else:
                    logger.warning("最終確認: ログインしていません")
                    if progress_callback:
                        progress_callback("ログイン確認: ログインしていません")
                    return False
                
        except Exception as e:
            logger.error(f"ログイン処理中にエラーが発生しました: {e}", exc_info=True)
            if progress_callback:
                progress_callback(f"ログイン処理中にエラーが発生しました: {e}")
            return False
    
    def _url_matches_pattern(self, url, pattern):
        """URLがパターンにマッチするかを確認"""
        return pattern in url

    async def manual_login(self, progress_callback=None) -> bool:
        """
        完全に手動でのGoogleアカウントログイン
        ユーザーにブラウザを表示し、手動でログインしてもらいます。
        ログインが成功したら、storage_stateを保存します。
        """
        logger.info("手動ログインモードを開始します")
        
        if progress_callback:
            progress_callback("手動ログインモードを開始します。ブラウザウィンドウでログインしてください...")
            
        try:
            page = await self.context.new_page()
            
            # Googleアカウントのホームページに移動
            await page.goto("https://accounts.google.com", timeout=30000)
            
            if progress_callback:
                progress_callback("ブラウザウィンドウが開きました。ログインを完了してください。完了したら「ログイン完了」ボタンをクリックしてください...")
            
            # ユーザーにガイダンスを表示
            logger.info("Googleアカウントにログインしてください。ログインが完了したら「ログイン完了」ボタンをクリックしてください。")
            
            # コンソールメッセージリスナーを設定
            login_completed = False
            
            def console_listener(msg):
                nonlocal login_completed
                if msg.text == 'login_complete':
                    login_completed = True
            
            page.on('console', console_listener)
            
            # ログイン完了ボタンをページに追加
            await page.evaluate("""
            () => {
                // すでに存在している場合は削除
                const existingButton = document.getElementById('login_complete_button');
                if (existingButton) {
                    existingButton.remove();
                }
                
                // スタイルシートを追加
                const style = document.createElement('style');
                style.textContent = `
                    #login_complete_overlay {
                        position: fixed;
                        bottom: 20px;
                        right: 20px;
                        z-index: 9999;
                        background: rgba(255, 255, 255, 0.9);
                        padding: 15px;
                        border-radius: 8px;
                        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
                        font-family: Arial, sans-serif;
                    }
                    #login_complete_button {
                        background: #4285F4;
                        color: white;
                        border: none;
                        padding: 10px 20px;
                        border-radius: 4px;
                        font-size: 14px;
                        cursor: pointer;
                        font-weight: bold;
                    }
                    #login_complete_button:hover {
                        background: #3367D6;
                    }
                    #login_complete_message {
                        margin-bottom: 10px;
                        font-size: 14px;
                    }
                `;
                document.head.appendChild(style);
                
                // オーバーレイとボタンを作成
                const overlay = document.createElement('div');
                overlay.id = 'login_complete_overlay';
                
                const message = document.createElement('div');
                message.id = 'login_complete_message';
                message.textContent = 'ログインが完了したら、このボタンをクリックしてください:';
                
                const button = document.createElement('button');
                button.id = 'login_complete_button';
                button.textContent = 'ログイン完了';
                button.onclick = function() {
                    console.log('login_complete');
                    this.textContent = '処理中...';
                    this.disabled = true;
                };
                
                overlay.appendChild(message);
                overlay.appendChild(button);
                document.body.appendChild(overlay);
            }
            """)
            
            # ボタンクリックを待機
            timeout_seconds = 600  # 10分間のタイムアウト
            start_time = time.time()
            
            while time.time() - start_time < timeout_seconds:
                if login_completed:
                    logger.info("ログイン完了ボタンがクリックされました")
                    break
                
                # 1秒待機
                await asyncio.sleep(1)
                
                # ページが閉じられたかチェック
                if page.is_closed():
                    logger.info("ページが閉じられました")
                    break
            
            if not login_completed and not page.is_closed():
                logger.warning("タイムアウト: ログイン完了ボタンがクリックされませんでした")
                try:
                    if not page.is_closed():
                        await page.close()
                except Exception as e:
                    logger.error(f"ページを閉じる際のエラー: {e}")
                return False
            
            # ログイン確認前に少し待機（ログイン処理完了を待つ）
            await asyncio.sleep(3)
            
            # ログイン状態を確認
            is_logged_in = await self.is_logged_in()
            
            if is_logged_in:
                logger.info("手動ログインが成功しました")
                if progress_callback:
                    progress_callback("手動ログインが成功しました")
                try:
                    if not page.is_closed():
                        await page.close()
                except Exception as e:
                    logger.error(f"ページを閉じる際のエラー: {e}")
                return True
            else:
                logger.warning("手動ログイン後もログインが確認できません")
                if progress_callback:
                    progress_callback("ログイン状態を確認できませんでした。再度試してください。")
                try:
                    if not page.is_closed():
                        await page.close()
                except Exception as e:
                    logger.error(f"ページを閉じる際のエラー: {e}")
                return False
            
        except Exception as e:
            logger.error(f"手動ログイン処理中にエラーが発生しました: {e}", exc_info=True)
            if progress_callback:
                progress_callback(f"エラーが発生しました: {e}")
            return False


class GBPUploader:
    """Google Business Profile (GBP) に画像をアップロードするクラス"""
    
    def __init__(self, context: BrowserContext):
        self.context = context
        self.gbp_selectors = get_gbp_selectors()
        self.settings = get_settings()
        self.upload_wait_seconds = self.settings.get('upload_wait_seconds', 5)
    
    async def upload_images(self, gbp_url: str, image_paths: List[str], progress_callback=None) -> bool:
        """GBPに画像をアップロード"""
        logger.info(f"GBP投稿画面にアクセス中: {gbp_url}")
        
        if progress_callback:
            progress_callback("GBP投稿画面にアクセス中...")
        
        try:
            page = await self.context.new_page()
            await page.goto(gbp_url)
            
            # 写真追加ボタンが表示されるまで待機
            add_photo_selector = self.gbp_selectors.get('add_photo_button')
            logger.debug(f"写真追加ボタンのセレクタ: {add_photo_selector}")
            
            try:
                await page.wait_for_selector(add_photo_selector, timeout=10000)
                logger.info("写真追加ボタンが見つかりました")
            except TimeoutError:
                logger.warning("写真追加ボタンが見つかりません。ページ構造が変更された可能性があります")
                await page.screenshot(path="error_screenshot.png")
                logger.info("エラー状態のスクリーンショットを保存しました: error_screenshot.png")
                await page.close()
                return False
            
            # 写真追加ボタンをクリック
            await page.click(add_photo_selector)
            logger.info("写真追加ボタンをクリックしました")
            
            if progress_callback:
                progress_callback("写真アップロードダイアログを準備中...")
            
            # アップロードモーダルが表示されるまで待機
            upload_modal_selector = self.gbp_selectors.get('upload_modal')
            await page.wait_for_selector(upload_modal_selector, timeout=10000)
            
            # ファイル入力要素が表示されるまで待機
            file_input_selector = self.gbp_selectors.get('file_input')
            await page.wait_for_selector(file_input_selector, timeout=10000)
            
            # ファイルをアップロード
            element = await page.query_selector(file_input_selector)
            if element:
                logger.info(f"{len(image_paths)}枚の画像をアップロード中...")
                
                if progress_callback:
                    progress_callback(f"{len(image_paths)}枚の画像をアップロード中...")
                
                # 画像ファイルのパスリストをPlaywrightのsetInputFiles関数に渡す
                await element.set_input_files(image_paths)
                logger.info("画像ファイルを選択しました")
                
                # 「投稿」ボタンが有効になるまで待機
                post_button_selector = self.gbp_selectors.get('post_button')
                await page.wait_for_selector(post_button_selector, timeout=30000)
                
                # 少し待機（画像のプレビューが表示されるまで）
                await asyncio.sleep(self.upload_wait_seconds)
                
                if progress_callback:
                    progress_callback("写真を投稿中...")
                
                # 「投稿」ボタンをクリック
                await page.click(post_button_selector)
                logger.info("投稿ボタンをクリックしました")
                
                # 投稿完了を待機（適切な完了セレクタがない場合は一定時間待機）
                await asyncio.sleep(5)
                
                logger.info("画像の投稿が完了しました")
                await page.close()
                return True
            else:
                logger.error("ファイル入力要素が見つかりません")
                await page.close()
                return False
            
        except Exception as e:
            logger.error(f"画像アップロード中にエラーが発生しました: {e}", exc_info=True)
            try:
                await page.screenshot(path="error_screenshot.png")
                logger.info("エラー状態のスクリーンショットを保存しました: error_screenshot.png")
                await page.close()
            except:
                pass
            return False


async def check_google_login_status() -> bool:
    """Googleログイン状態をチェック"""
    pw_manager = PlaywrightManager()
    try:
        context = await pw_manager.start()
        auth_manager = GoogleAuthManager(context)
        is_logged_in = await auth_manager.is_logged_in()
        await pw_manager.close()
        return is_logged_in
    except Exception as e:
        logger.error(f"ログイン状態チェック中にエラーが発生しました: {e}", exc_info=True)
        await pw_manager.close()
        return False


async def perform_google_login(progress_callback=None, browser_type='firefox') -> bool:
    """Googleアカウントにログイン"""
    logger.info("Googleログインページを開きます...")
    
    pw_manager = PlaywrightManager(browser_type=browser_type)
    try:
        context = await pw_manager.start()
        auth_manager = GoogleAuthManager(context)
        
        # すでにログインしているか確認
        is_logged_in = await auth_manager.is_logged_in()
        if is_logged_in:
            logger.info("すでにログインしています")
            if progress_callback:
                progress_callback("すでにログインしています")
            await pw_manager.close()
            return True
        
        # ログイン実行
        login_success = await auth_manager.login(progress_callback)
        if login_success:
            await pw_manager.save_storage_state()
        
        await pw_manager.close()
        return login_success
    except Exception as e:
        logger.error(f"ログイン処理中にエラーが発生しました: {e}", exc_info=True)
        await pw_manager.close()
        return False


async def upload_images_to_gbp(gbp_url: str, image_paths: List[str], progress_callback=None) -> bool:
    """GBPに画像をアップロード"""
    pw_manager = PlaywrightManager()
    try:
        context = await pw_manager.start()
        
        # ログイン状態を確認
        auth_manager = GoogleAuthManager(context)
        is_logged_in = await auth_manager.is_logged_in()
        
        if not is_logged_in:
            logger.warning("ログインしていないため、アップロードを中止します")
            await pw_manager.close()
            return False
        
        # 画像アップロード実行
        uploader = GBPUploader(context)
        upload_success = await uploader.upload_images(gbp_url, image_paths, progress_callback)
        
        # 成功した場合はstorage_stateを保存（Cookieの更新）
        if upload_success:
            await pw_manager.save_storage_state()
        
        await pw_manager.close()
        return upload_success
    except Exception as e:
        logger.error(f"GBPアップロード処理中にエラーが発生しました: {e}", exc_info=True)
        await pw_manager.close()
        return False


async def perform_manual_login(progress_callback=None) -> bool:
    """手動Googleログイン処理を実行"""
    logger.info("手動Googleログインを開始します...")
    
    # ブラウザはヘッドレスモードをオフにして起動する必要がある
    pw_manager = PlaywrightManager(browser_type='chromium')
    try:
        # ヘッドレスモードを強制的にオフにする
        pw_manager.headless = False
        
        context = await pw_manager.start()
        auth_manager = GoogleAuthManager(context)
        
        # 手動ログイン実行
        login_success = await auth_manager.manual_login(progress_callback)
        
        # 成功したらstorage_stateを保存
        if login_success:
            await pw_manager.save_storage_state()
            logger.info(f"ログイン情報を保存しました: {pw_manager.storage_state_path}")
            if progress_callback:
                progress_callback(f"ログイン情報を保存しました: {pw_manager.storage_state_path}")
        
        await pw_manager.close()
        return login_success
    except Exception as e:
        logger.error(f"手動ログイン処理中にエラーが発生しました: {e}", exc_info=True)
        await pw_manager.close()
        return False


# 非同期関数を同期的に実行するヘルパー関数
def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# 同期バージョンの関数（GUIから呼び出し用）
def check_login() -> bool:
    """同期バージョンのGoogleログイン状態チェック"""
    return run_async(check_google_login_status())


def login_to_google(progress_callback=None) -> bool:
    """同期バージョンのGoogleログイン実行"""
    # まずはFirefoxでログインを試行
    success = run_async(perform_google_login(progress_callback, browser_type='firefox'))
    
    # Firefoxでのログインが失敗した場合、Chromiumで試行
    if not success:
        if progress_callback:
            progress_callback("Firefoxでのログインに失敗しました。Chromiumで再試行します...")
        success = run_async(perform_google_login(progress_callback, browser_type='chromium'))
    
    return success


def upload_to_gbp(gbp_url: str, image_paths: List[str], progress_callback=None) -> bool:
    """同期バージョンのGBPアップロード実行"""
    return run_async(upload_images_to_gbp(gbp_url, image_paths, progress_callback))


def manual_login(progress_callback=None) -> bool:
    """同期バージョンの手動Googleログイン実行"""
    return run_async(perform_manual_login(progress_callback))


# テスト用のメイン処理
if __name__ == "__main__":
    # テスト用の引数処理
    import argparse
    
    parser = argparse.ArgumentParser(description='Google Business Profileに画像をアップロードするツール')
    parser.add_argument('--check', action='store_true', help='Googleログイン状態をチェック')
    parser.add_argument('--login', action='store_true', help='Googleにログイン')
    parser.add_argument('--manual-login', action='store_true', help='手動モードでGoogleにログイン')
    parser.add_argument('--upload', help='GBP URLを指定して画像をアップロード')
    parser.add_argument('--images', nargs='+', help='アップロードする画像ファイルのパス（複数指定可）')
    
    args = parser.parse_args()
    
    if args.check:
        print("Googleログイン状態をチェック中...")
        is_logged_in = check_login()
        print(f"ログイン状態: {'ログイン済み' if is_logged_in else 'ログインしていません'}")
    
    elif args.login:
        print("Googleログインページを開きます...")
        success = login_to_google()
        print(f"ログイン結果: {'成功' if success else '失敗'}")
    
    elif args.manual_login:
        print("手動Googleログインモードを開始します...")
        success = manual_login()
        print(f"手動ログイン結果: {'成功' if success else '失敗'}")
    
    elif args.upload and args.images:
        print(f"GBP URL: {args.upload}")
        print(f"アップロードする画像: {args.images}")
        success = upload_to_gbp(args.upload, args.images)
        print(f"アップロード結果: {'成功' if success else '失敗'}")
    
    else:
        parser.print_help() 
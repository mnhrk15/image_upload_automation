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
    
    async def is_logged_in(self, page: Optional[Page] = None) -> bool:
        """Googleにログインしているかチェック (既存Pageオブジェクト利用可)"""
        logger.info("ログイン状態を確認中...")
        check_page = page # 渡されたページを使う
        should_close_page = False
        
        try:
            if check_page is None:
                # ページが渡されなかった場合（独立したチェックなど）は新規作成
                logger.debug("is_logged_in: 新規ページを作成してチェックします")
                check_page = await self.context.new_page()
                should_close_page = True
            else:
                logger.debug("is_logged_in: 既存のページを使用してチェックします")

            # ログイン確認ページに移動（または現在のURLを確認）
            # すでにGoogleドメインにいるかもしれないので、現在地を確認
            current_url = check_page.url
            if "accounts.google.com" not in current_url:
                 logger.debug(f"is_logged_in: accounts.google.com へ移動します (現在地: {current_url})")
                 await check_page.goto("https://accounts.google.com/signin/v2/identifier", wait_until='networkidle')
                 current_url = check_page.url # 移動後のURLを再取得
            
            logger.debug(f"ログインチェック中のURL: {current_url}")
            
            # ログイン済みの判定 (バックスラッシュによる行継続を修正)
            is_logged_in = ("myaccount.google.com" in current_url or 
                           "accounts.google.com/ManageAccount" in current_url or 
                           "accounts.google.com/ServiceLogin" not in current_url)
            
            if is_logged_in:
                logger.info("Googleにログイン済みです")
            else:
                logger.info("Googleにログインしていません")
            
            return is_logged_in
            
        except Exception as e:
            logger.error(f"ログイン状態の確認中にエラーが発生しました: {e}", exc_info=True)
            return False
        finally:
            # このメソッド内で新規作成したページのみ閉じる
            if should_close_page and check_page and not check_page.is_closed():
                logger.debug("is_logged_in: 新規作成したチェック用ページを閉じます")
                await check_page.close()

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
        self.default_timeout = 60000 # 60秒
    
    async def _save_error_page(self, page: Page, filename_base: str = "error"):
        """エラー発生時のページ状態を保存するヘルパー関数"""
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"{filename_base}_screenshot_{timestamp}.png"
            html_path = f"{filename_base}_page_{timestamp}.html"
            await page.screenshot(path=screenshot_path)
            logger.info(f"エラー状態のスクリーンショットを保存しました: {screenshot_path}")
            html_content = await page.content()
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            logger.info(f"エラー状態のHTMLを保存しました: {html_path}")
        except Exception as save_error:
            logger.error(f"エラーページの保存中にエラー: {save_error}")

    async def upload_images(self, gbp_url: str, image_paths: List[str], page: Optional[Page] = None, progress_callback=None) -> bool:
        """GBPに画像をアップロード (ファイル選択 iframe 対応, expect_file_chooser使用)"""
        
        upload_page = page 
        should_create_page = False
        
        if upload_page is None:
            logger.warning("upload_images: Pageオブジェクトが渡されませんでした。新規作成します。")
            should_create_page = True
            # このケースは現在のフローでは発生しない想定
        
        logger.info(f"GBP投稿画面処理を開始 (Page: {'新規' if should_create_page else '既存'})")
        
        # --- セレクタを config.json から読み込む --- 
        add_photo_selector = self.gbp_selectors.get('photo_upload', {}).get('add_button', 'a:has-text("写真を追加")') # デフォルト値も設定
        file_upload_iframe_selector = self.gbp_selectors.get('photo_upload', {}).get('upload_iframe', 'iframe[src*="/promote/photos/add"]')
        select_files_button_selector = self.gbp_selectors.get('photo_upload', {}).get('select_button', 'button:has-text("画像と動画を選択")')
        # post_button_selector は不要
        # file_input_selector も不要
        # upload_modal_selector も不要

        try:
            if should_create_page:
                upload_page = await self.context.new_page()
                logger.debug(f"新規ページでURLへ移動: {gbp_url}")
                await upload_page.goto(gbp_url, timeout=self.default_timeout, wait_until='networkidle')
                logger.debug("ページ移動完了 (networkidle)。")
            
            logger.debug(f"現在のページ ({upload_page.url}) でアップロード処理を開始します")
            
            # --- 1. 写真追加ボタンをクリック (メインページ) ---
            try:
                logger.debug(f"写真追加ボタンが表示されるのを待機中... セレクタ: {add_photo_selector}, Timeout={self.default_timeout}ms")
                await upload_page.wait_for_selector(add_photo_selector, timeout=self.default_timeout, state='visible')
                logger.info("写真追加ボタンが見つかりました")
            except TimeoutError:
                logger.warning("写真追加ボタンが見つかりません。ページ構造が変更されたか、ログイン状態が不正な可能性があります")
                await self._save_error_page(upload_page, "error_add_button")
                return False 
            
            logger.debug(f"写真追加ボタンをクリックします: {add_photo_selector}")
            await upload_page.click(add_photo_selector)
            logger.info("写真追加ボタンをクリックしました")

            # --- 2. ファイル選択 iframe を待機・特定 --- 
            try:
                logger.info(f"ファイル選択 iframe ({file_upload_iframe_selector}) の出現を待機中...")
                await upload_page.wait_for_selector(file_upload_iframe_selector, timeout=self.default_timeout, state='visible')
                logger.info("ファイル選択 iframe が表示されました。")
                upload_frame_locator = upload_page.frame_locator(file_upload_iframe_selector)
                logger.debug("ファイル選択 iframe の FrameLocator を取得しました。")
            except TimeoutError:
                 logger.warning("ファイル選択 iframe が見つかりませんでした（タイムアウト）。")
                 await self._save_error_page(upload_page, "error_file_upload_iframe")
                 return False

            # --- 3. iframe 内でアップロード操作 (expect_file_chooser を使用) --- 
            if progress_callback:
                progress_callback("写真アップロードダイアログを準備中...")
            
            # 新しい方法: expect_file_chooser
            try:
                logger.info("ファイルチューザーの準備 (ページ全体で待機)...")
                async with upload_page.expect_file_chooser(timeout=self.default_timeout) as fc_info:
                    logger.debug(f"「画像と動画を選択」ボタンをクリックします (iframe 内): {select_files_button_selector}")
                    await upload_frame_locator.locator(select_files_button_selector).click()
                    logger.info("「画像と動画を選択」ボタンをクリックしました (iframe 内)")
                
                file_chooser = await fc_info.value
                logger.info(f"{len(image_paths)}枚の画像をファイルチューザーに設定中...")
                if progress_callback:
                    progress_callback(f"{len(image_paths)}枚の画像をアップロード中...")
                
                await file_chooser.set_files(image_paths)
                logger.info("画像ファイルを選択しました (ファイルチューザー経由)")
                
                # upload_complete_wait = self.upload_wait_seconds # 設定値を使う
                # logger.info(f"ファイル選択完了、アップロード完了まで {upload_complete_wait} 秒待機します...")
                # await asyncio.sleep(upload_complete_wait)
                
                # --- 動的待機: アップロード iframe が閉じるのを待つ --- 
                upload_complete_timeout = self.default_timeout * 2 # タイムアウトを長めに設定 (例: 2分)
                logger.info(f"ファイル選択完了、アップロード完了 (iframe が閉じる) を待機します... Timeout={upload_complete_timeout}ms")
                try:
                    await upload_page.wait_for_selector(file_upload_iframe_selector, state='hidden', timeout=upload_complete_timeout)
                    logger.info("ファイルアップロード iframe が閉じました。アップロード完了と見なします。")
                except TimeoutError:
                    logger.warning("アップロード完了待機中にタイムアウトしました (iframe が閉じませんでした)。プロセスは完了している可能性があります。")
                    # タイムアウトしても、成功とみなして続行するか、エラーにするか選択可能
                    # ここでは警告ログのみ出力し、成功として扱う
                
                logger.info("画像の投稿プロセスが完了したと見なします (投稿ボタンなし)")
                return True

            except TimeoutError:
                logger.error("ファイルチューザーが開かれるのを待機中にタイムアウトしました。ボタンが見つからないか、クリックに失敗した可能性があります。")
                await self._save_error_page(upload_page, "error_file_chooser_timeout")
                return False
            except Exception as fc_error:
                logger.error(f"ファイルチューザーの処理中にエラー: {fc_error}", exc_info=True)
                await self._save_error_page(upload_page, "error_file_chooser")
                return False

        except Exception as e:
            logger.error(f"画像アップロード中に予期せぬエラーが発生しました: {e}", exc_info=True)
            if upload_page and not upload_page.is_closed():
                 await self._save_error_page(upload_page, "error_unexpected_upload")
            return False
        finally:
            if should_create_page and upload_page and not upload_page.is_closed():
                logger.debug("upload_images: 新規作成したアップロード用ページを閉じます")
                await upload_page.close()


async def check_google_login_status(context: BrowserContext) -> bool:
    """Googleログイン状態をチェック (Contextを受け取る)"""
    try:
        auth_manager = GoogleAuthManager(context)
        is_logged_in = await auth_manager.is_logged_in()
        return is_logged_in
    except Exception as e:
        logger.error(f"ログイン状態チェック中にエラーが発生しました: {e}", exc_info=True)
        return False


async def perform_google_login(context: BrowserContext, storage_state_path: str, progress_callback=None) -> bool:
    """Googleアカウントにログイン (Contextを受け取る)"""
    logger.info("Googleログイン処理を開始します (Context使用)...")
    login_success = False
    try:
        auth_manager = GoogleAuthManager(context)
        
        is_logged_in = await auth_manager.is_logged_in()
        if is_logged_in:
            logger.info("すでにログインしています")
            if progress_callback:
                progress_callback("すでにログインしています")
            login_success = True
        else:
            login_success = await auth_manager.login(progress_callback)
            if login_success:
                pass
        
        return login_success
    except Exception as e:
        logger.error(f"ログイン処理中にエラーが発生しました: {e}", exc_info=True)
        return False


async def perform_manual_login(context: BrowserContext, progress_callback=None) -> bool:
    """手動Googleログイン処理を実行 (Contextを受け取る)"""
    logger.info("手動Googleログイン処理を開始します (Context使用)...")
    login_success = False
    try:
        auth_manager = GoogleAuthManager(context)
        login_success = await auth_manager.manual_login(progress_callback)
        
        return login_success
    except Exception as e:
        logger.error(f"手動ログイン処理中にエラーが発生しました: {e}", exc_info=True)
        return False


# 非同期関数を同期的に実行するヘルパー関数
def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# 同期バージョンの関数（GUIから呼び出し用）- Playwrightライフサイクルを管理
def check_login() -> bool:
    """同期バージョンのGoogleログイン状態チェック (PWライフサイクル管理)"""
    pw_manager = PlaywrightManager()
    try:
        async def main():
            context = await pw_manager.start()
            return await check_google_login_status(context)
        return run_async(main())
    finally:
        async def close_pw():
            await pw_manager.close()
        run_async(close_pw())


def login_to_google(progress_callback=None) -> bool:
    """同期バージョンのGoogleログイン実行 (PWライフサイクル管理)"""
    pw_manager = PlaywrightManager(browser_type='chromium')
    login_success = False
    try:
        async def main():
            nonlocal login_success
            context = await pw_manager.start()
            login_success = await perform_google_login(context, pw_manager.storage_state_path, progress_callback)
            if login_success:
                await pw_manager.save_storage_state()
            return login_success
        return run_async(main())
    finally:
        async def close_pw():
            await pw_manager.close()
        run_async(close_pw())


def upload_to_gbp(gbp_url: str, image_paths: List[str], progress_callback=None) -> bool:
    """同期バージョンのGBPアップロード実行 (単一ページフロー)"""
    pw_manager = PlaywrightManager()
    try:
        # 修正された非同期ロジックを実行
        return run_async(_async_upload_logic(pw_manager, gbp_url, image_paths, progress_callback))
    finally:
        # Playwright Manager を閉じる
        logger.debug("Upload_to_gbp (sync wrapper): Closing Playwright Manager.")
        run_async(pw_manager.close())


def manual_login(progress_callback=None) -> bool:
    """同期バージョンの手動Googleログイン実行 (PWライフサイクル管理)"""
    pw_manager = PlaywrightManager(browser_type='chromium')
    pw_manager.headless = False
    login_success = False
    try:
        async def main():
            nonlocal login_success
            context = await pw_manager.start()
            login_success = await perform_manual_login(context, progress_callback)
            if login_success:
                logger.info(f"手動ログイン成功、ログイン情報を保存: {pw_manager.storage_state_path}")
                await context.storage_state(path=pw_manager.storage_state_path)
            return login_success
        return run_async(main())
    finally:
        async def close_pw():
            await pw_manager.close()
        run_async(close_pw())


# 新しい非同期ヘルパー関数
async def _async_upload_logic(pw_manager: PlaywrightManager, gbp_url: str, image_paths: List[str], progress_callback=None) -> bool:
    """単一ページでログイン確認からアップロードまで行う非同期ロジック (セレクタをconfigから読み込み)"""
    context = None
    page = None
    upload_success = False
    
    # --- セレクタを config.json から読み込む --- 
    gbp_selectors = get_gbp_selectors()
    owner_check_button_selector = gbp_selectors.get('owner_check', {}).get('owner_button', 'a[jsname="ndJ4N"]:has-text("このビジネスのオーナーですか？")')
    iframe_selector = gbp_selectors.get('owner_check', {}).get('iframe', 'iframe[src^="/local/business/setup/create"]')
    continue_button_selector = gbp_selectors.get('owner_check', {}).get('continue_button', 'button:has-text("続行")')
    add_photo_selector = gbp_selectors.get('photo_upload', {}).get('add_button', 'a:has-text("写真を追加")') # 写真追加ボタンセレクタもここで取得

    try:
        context = await pw_manager.start()
        logger.debug("Async upload logic: Context started.")
        page = await context.new_page()
        logger.debug("Async upload logic: Page created.")

        # --- 1. ログイン状態を確認 --- 
        auth_manager = GoogleAuthManager(context)
        logger.debug("Async upload logic: Checking login status on the created page...")
        is_logged_in = await auth_manager.is_logged_in(page=page) 
        if not is_logged_in:
            logger.warning("ログインしていないため、アップロードを中止します")
            await page.close()
            return False
        
        # --- 2. GBP URLへ移動 --- 
        logger.info(f"ログイン確認完了。同じページでGBP URLへ移動します: {gbp_url}")
        await page.goto(gbp_url, timeout=60000, wait_until='networkidle')
        logger.debug(f"GBP URLへの移動完了: {page.url}")

        # --- 2.5 オーナー確認ステップ / スキップ判定 ---
        owner_check_visible = False
        add_photo_visible = False

        # まず「オーナー確認」ボタンの存在を確認 (短いタイムアウト)
        try:
            logger.info(f"「このビジネスのオーナーですか？」ボタンの存在を確認中 (セレクタ: {owner_check_button_selector})...")
            await page.wait_for_selector(owner_check_button_selector, timeout=1000, state='visible')
            owner_check_visible = True
            logger.info("「このビジネスのオーナーですか？」ボタンが見つかりました。")
        except TimeoutError:
            logger.info("「このビジネスのオーナーですか？」ボタンは見つかりませんでした。次に「写真を追加」ボタンを確認します。")
        except Exception as e:
            logger.warning(f"「このビジネスのオーナーですか？」ボタンの表示確認中にエラー: {e}")

        # 「オーナー確認」ボタンが見つからなかった場合のみ、「写真を追加」ボタンを確認
        if not owner_check_visible:
            try:
                logger.info(f"「写真を追加」ボタンの存在を確認中 (セレクタ: {add_photo_selector})...")
                await page.wait_for_selector(add_photo_selector, timeout=1000, state='visible') # タイムアウトはさらに短くても良いかも
                add_photo_visible = True
                logger.info("「写真を追加」ボタンが見つかりました。")
            except TimeoutError:
                logger.info("「写真を追加」ボタンも見つかりませんでした。")
            except Exception as e:
                logger.warning(f"「写真を追加」ボタンの表示確認中にエラー: {e}")

        # オーナー確認を実行する条件: 「オーナー確認」ボタンが存在する場合
        if owner_check_visible:
            logger.info("オーナー確認ステップを実行します。")
            try:
                # --- オーナー確認の実際の処理 ---
                logger.info("「このビジネスのオーナーですか？」ボタンをクリックします。")
                await page.click(owner_check_button_selector)

                logger.info(f"オーナー確認用 iframe の出現を待機中 (セレクタ: {iframe_selector})...")
                await page.wait_for_selector(iframe_selector, timeout=15000, state='visible')
                logger.info("オーナー確認用 iframe が表示されました。")
                frame_locator = page.frame_locator(iframe_selector)
                logger.debug("iframe の FrameLocator を取得しました。")

                logger.info(f"iframe 内の「続行」ボタンを検索中 (セレクタ: {continue_button_selector})...")
                await frame_locator.locator(continue_button_selector).wait_for(state='visible', timeout=30000)
                logger.info("iframe 内の「続行」ボタンを発見、クリックします。")
                await frame_locator.locator(continue_button_selector).click()

                # --- 動的待機: オーナー確認 iframe が閉じるのを待つ ---
                owner_iframe_close_timeout = 30000 # 30秒
                logger.info(f"オーナー確認ステップ完了。iframe が閉じるのを待機します... Timeout={owner_iframe_close_timeout}ms")
                try:
                    await page.wait_for_selector(iframe_selector, state='hidden', timeout=owner_iframe_close_timeout)
                    logger.info("オーナー確認 iframe が閉じました。")
                except TimeoutError:
                    logger.warning("オーナー確認 iframe が閉じるのを待機中にタイムアウトしました。続行します。")

            except TimeoutError:
                logger.warning("オーナー確認ステップのいずれかの要素が見つかりませんでした（タイムアウト）。続行します。")
            except Exception as owner_check_error:
                logger.warning(f"オーナー確認ステップで予期せぬエラー: {owner_check_error}", exc_info=True)

        elif add_photo_visible:
            logger.info("「オーナー確認」ボタンがなく「写真を追加」ボタンが見つかったため、オーナー確認をスキップします。")
        else:
            logger.warning("「オーナー確認」ボタンも「写真を追加」ボタンも見つかりませんでした。そのままアップロード処理に進みます。")


        # --- 3. アップロード実行 (元のページコンテキストに戻っているはず) ---
        logger.debug("アップロード処理を開始します (メインページ)") # ログメッセージ調整
        uploader = GBPUploader(context) # GBPUploader をここでインスタンス化
        # upload_images は context を共有する uploader インスタンスから呼び出す
        upload_success = await uploader.upload_images(gbp_url, image_paths, page=page, progress_callback=progress_callback)
        
        # --- 4. 成功時のみ storage_state を保存 --- 
        if upload_success:
            logger.debug("アップロード成功のため、storage_state を保存します")
            await pw_manager.save_storage_state()
            
        return upload_success

    except Exception as e:
        logger.error(f"非同期アップロードロジック全体でエラー: {e}", exc_info=True)
        # GBPUploader内でエラーページ保存を試みるが、ここでも念のため
        if page and not page.is_closed():
            try:
                # PlaywrightManagerに移動した方が良い
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                await page.screenshot(path=f"error_async_logic_{timestamp}.png")
            except:
                 pass
        return False
    finally:
        # ページがまだ開いていれば閉じる
        if page and not page.is_closed():
            logger.debug("Async upload logic: Closing page in finally block.")
            await page.close()
        # Contextの終了は呼び出し元 (upload_to_gbp) の finally で行われる


# テスト用のメイン処理 (コメントアウト済み)
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
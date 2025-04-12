import os
import sys
import logging
import time
from typing import List, Dict, Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QLineEdit, QPushButton, QProgressBar,
    QScrollArea, QGridLayout, QCheckBox, QMessageBox,
    QTextEdit, QGroupBox, QStatusBar, QSizePolicy, QFrame
)
from PyQt6.QtCore import Qt, QSize, QThreadPool, QRunnable, pyqtSignal, QObject, pyqtSlot
from PyQt6.QtGui import QPixmap, QImage, QIcon, QFont

from src.config_manager import get_settings
from src.hpb_scraper import get_salon_name, fetch_latest_style_images, download_images

# ロギング設定
logger = logging.getLogger(__name__)

# ----- ワーカースレッド用のクラス -----

class WorkerSignals(QObject):
    """ワーカースレッドからシグナルを発行するためのクラス"""
    started = pyqtSignal()
    finished = pyqtSignal()
    error = pyqtSignal(str)
    progress = pyqtSignal(int, str)
    result = pyqtSignal(object)
    log = pyqtSignal(str)

class Worker(QRunnable):
    """バックグラウンドでタスクを実行するワーカークラス"""
    
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        
    @pyqtSlot()
    def run(self):
        """ワーカーの実行メソッド"""
        self.signals.started.emit()
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(result)
        except Exception as e:
            logger.error(f"ワーカースレッドでエラーが発生しました: {e}", exc_info=True)
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()

# ----- メインウィンドウクラス -----

class MainWindow(QMainWindow):
    """アプリケーションのメインウィンドウ"""
    
    def __init__(self):
        super().__init__()
        
        self.threadpool = QThreadPool()
        logger.debug(f"利用可能なスレッド数: {self.threadpool.maxThreadCount()}")
        
        self.salon_name = ""  # サロン名を保存
        self.image_paths = []  # ダウンロードした画像のパスを保存
        self.image_checkboxes = []  # 画像のチェックボックスを保存
        
        self.init_ui()
    
    def init_ui(self):
        """UIの初期化"""
        self.setWindowTitle("HotPepper Beauty 画像投稿ツール")
        self.setMinimumSize(800, 600)
        
        # メインウィジェットとレイアウト
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        self.setCentralWidget(main_widget)
        
        # --- URL入力セクション ---
        url_group = QGroupBox("URL設定")
        url_layout = QVBoxLayout(url_group)
        
        # HPB URL入力
        hpb_layout = QHBoxLayout()
        hpb_label = QLabel("HPB URL:")
        self.hpb_url_input = QLineEdit()
        self.hpb_url_input.setPlaceholderText("https://beauty.hotpepper.jp/slnH000xxxxxx/")
        self.salon_name_label = QLabel("")
        hpb_layout.addWidget(hpb_label)
        hpb_layout.addWidget(self.hpb_url_input, 1)
        hpb_layout.addWidget(self.salon_name_label)
        url_layout.addLayout(hpb_layout)
        
        # GBP URL入力
        gbp_layout = QHBoxLayout()
        gbp_label = QLabel("GBP URL:")
        self.gbp_url_input = QLineEdit()
        self.gbp_url_input.setPlaceholderText("Google投稿画面のURL")
        gbp_layout.addWidget(gbp_label)
        gbp_layout.addWidget(self.gbp_url_input, 1)
        url_layout.addLayout(gbp_layout)
        
        main_layout.addWidget(url_group)
        
        # --- 操作ボタンセクション ---
        button_layout = QHBoxLayout()
        
        # Googleログインボタン
        self.login_button = QPushButton("Googleにログイン/状態確認")
        self.login_button.clicked.connect(self.check_google_login)
        button_layout.addWidget(self.login_button)
        
        # 画像取得ボタン
        self.fetch_button = QPushButton("画像を取得")
        self.fetch_button.clicked.connect(self.fetch_images)
        button_layout.addWidget(self.fetch_button)
        
        # 選択した画像を投稿ボタン
        self.upload_button = QPushButton("選択した画像を投稿")
        self.upload_button.clicked.connect(self.upload_selected_images)
        self.upload_button.setEnabled(False)
        button_layout.addWidget(self.upload_button)
        
        main_layout.addLayout(button_layout)
        
        # --- 画像表示セクション ---
        images_group = QGroupBox("ヘアスタイル画像")
        images_layout = QVBoxLayout(images_group)
        
        # スクロール可能な画像グリッドエリア
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        self.images_grid = QGridLayout(scroll_content)
        scroll_area.setWidget(scroll_content)
        images_layout.addWidget(scroll_area)
        
        # 全選択/全解除ボタン
        select_buttons_layout = QHBoxLayout()
        self.select_all_button = QPushButton("全て選択")
        self.select_all_button.clicked.connect(self.select_all_images)
        self.select_all_button.setEnabled(False)
        select_buttons_layout.addWidget(self.select_all_button)
        
        self.deselect_all_button = QPushButton("全て解除")
        self.deselect_all_button.clicked.connect(self.deselect_all_images)
        self.deselect_all_button.setEnabled(False)
        select_buttons_layout.addWidget(self.deselect_all_button)
        
        select_buttons_layout.addStretch()
        images_layout.addLayout(select_buttons_layout)
        
        main_layout.addWidget(images_group)
        
        # --- ステータス表示セクション ---
        status_group = QGroupBox("ステータス")
        status_layout = QVBoxLayout(status_group)
        
        # プログレスバー
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        status_layout.addWidget(self.progress_bar)
        
        # ログテキストエリア
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        status_layout.addWidget(self.log_text)
        
        main_layout.addWidget(status_group)
        
        # ステータスバー
        self.statusBar().showMessage("準備完了")
        
        # UIの初期化が完了したことをログに記録
        self.log_message("アプリケーションの準備が完了しました。")
    
    def log_message(self, message: str):
        """ログメッセージを表示エリアに追加"""
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        self.log_text.append(f"[{timestamp}] {message}")
        logger.info(message)
    
    def check_google_login(self):
        """Googleログイン状態をチェック"""
        self.log_message("Googleログイン状態を確認中...")
        # ここでPlaywrightを使用したログインチェック機能を実装（後で実装）
        self.statusBar().showMessage("Googleログイン機能は未実装です")
    
    def fetch_images(self):
        """HPBからスタイル画像を取得"""
        hpb_url = self.hpb_url_input.text().strip()
        if not hpb_url:
            QMessageBox.warning(self, "入力エラー", "HPB URLを入力してください")
            return
        
        self.log_message(f"HPB URL: {hpb_url} から画像を取得中...")
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("画像を取得中...")
        
        # UI要素を無効化
        self.fetch_button.setEnabled(False)
        self.upload_button.setEnabled(False)
        self.select_all_button.setEnabled(False)
        self.deselect_all_button.setEnabled(False)
        
        # Step 1: サロン名を取得
        worker = Worker(get_salon_name, hpb_url)
        worker.signals.result.connect(self.on_salon_name_fetched)
        worker.signals.error.connect(self.on_worker_error)
        worker.signals.finished.connect(lambda: self.progress_bar.setValue(20))
        self.threadpool.start(worker)
    
    def on_salon_name_fetched(self, salon_name):
        """サロン名取得完了後の処理"""
        if salon_name:
            self.salon_name = salon_name
            self.salon_name_label.setText(f"サロン名: {salon_name}")
            self.log_message(f"サロン名を取得しました: {salon_name}")
            
            # Step 2: 画像URLを取得
            hpb_url = self.hpb_url_input.text().strip()
            worker = Worker(fetch_latest_style_images, hpb_url)
            worker.signals.result.connect(self.on_image_urls_fetched)
            worker.signals.error.connect(self.on_worker_error)
            worker.signals.finished.connect(lambda: self.progress_bar.setValue(60))
            self.threadpool.start(worker)
        else:
            self.log_message("サロン名の取得に失敗しました")
            self.fetch_button.setEnabled(True)
            self.statusBar().showMessage("サロン名の取得に失敗しました")
            
    def on_image_urls_fetched(self, image_urls):
        """画像URL取得完了後の処理"""
        if image_urls and len(image_urls) > 0:
            self.log_message(f"{len(image_urls)}件の画像URLを取得しました")
            
            # Step 3: 画像をダウンロード
            worker = Worker(download_images, image_urls)
            worker.signals.result.connect(self.on_images_downloaded)
            worker.signals.error.connect(self.on_worker_error)
            worker.signals.finished.connect(lambda: self.progress_bar.setValue(90))
            self.threadpool.start(worker)
        else:
            self.log_message("画像URLの取得に失敗しました")
            self.fetch_button.setEnabled(True)
            self.statusBar().showMessage("画像URLの取得に失敗しました")
    
    def on_images_downloaded(self, image_paths):
        """画像ダウンロード完了後の処理"""
        if image_paths and len(image_paths) > 0:
            self.image_paths = image_paths
            self.log_message(f"{len(image_paths)}件の画像をダウンロードしました")
            self.display_images(image_paths)
            self.progress_bar.setValue(100)
            self.statusBar().showMessage(f"{len(image_paths)}件の画像を取得しました")
            
            # UI要素を有効化
            self.upload_button.setEnabled(True)
            self.select_all_button.setEnabled(True)
            self.deselect_all_button.setEnabled(True)
        else:
            self.log_message("画像のダウンロードに失敗しました")
            self.fetch_button.setEnabled(True)
            self.statusBar().showMessage("画像のダウンロードに失敗しました")
        
        self.fetch_button.setEnabled(True)
    
    def display_images(self, image_paths: List[str]):
        """ダウンロードした画像を表示エリアに表示"""
        # 既存の画像とチェックボックスをクリア
        for i in reversed(range(self.images_grid.count())): 
            self.images_grid.itemAt(i).widget().setParent(None)
        self.image_checkboxes.clear()
        
        # サムネイルサイズ
        thumbnail_size = 150
        
        # 画像を3列のグリッドで表示
        for idx, image_path in enumerate(image_paths):
            row, col = divmod(idx, 3)
            
            # 画像フレーム
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            frame_layout = QVBoxLayout(frame)
            
            # 画像のロードと表示
            pixmap = QPixmap(image_path)
            pixmap = pixmap.scaled(thumbnail_size, thumbnail_size, Qt.AspectRatioMode.KeepAspectRatio)
            image_label = QLabel()
            image_label.setPixmap(pixmap)
            image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            frame_layout.addWidget(image_label)
            
            # ファイル名表示
            filename = os.path.basename(image_path)
            name_label = QLabel(filename)
            name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            frame_layout.addWidget(name_label)
            
            # チェックボックス（デフォルトで選択済み）
            checkbox = QCheckBox("選択")
            checkbox.setChecked(True)
            checkbox.setProperty("image_path", image_path)
            self.image_checkboxes.append(checkbox)
            frame_layout.addWidget(checkbox)
            
            self.images_grid.addWidget(frame, row, col)
    
    def select_all_images(self):
        """全ての画像を選択"""
        for checkbox in self.image_checkboxes:
            checkbox.setChecked(True)
    
    def deselect_all_images(self):
        """全ての画像の選択を解除"""
        for checkbox in self.image_checkboxes:
            checkbox.setChecked(False)
    
    def upload_selected_images(self):
        """選択された画像をGBPに投稿"""
        gbp_url = self.gbp_url_input.text().strip()
        if not gbp_url:
            QMessageBox.warning(self, "入力エラー", "GBP URLを入力してください")
            return
        
        # 選択された画像のパスリストを作成
        selected_paths = []
        for checkbox in self.image_checkboxes:
            if checkbox.isChecked():
                selected_paths.append(checkbox.property("image_path"))
        
        if not selected_paths:
            QMessageBox.warning(self, "選択エラー", "投稿する画像を選択してください")
            return
        
        self.log_message(f"{len(selected_paths)}件の画像を投稿準備中...")
        self.log_message(f"GBP URL: {gbp_url}")
        
        # ここでPlaywrightを使用したGBP投稿機能を実装（後で実装）
        self.statusBar().showMessage("GBP投稿機能は未実装です")
    
    def on_worker_error(self, error_msg):
        """ワーカースレッドでエラーが発生した場合の処理"""
        self.log_message(f"エラーが発生しました: {error_msg}")
        self.statusBar().showMessage("エラーが発生しました")
        self.fetch_button.setEnabled(True)
        
    def closeEvent(self, event):
        """アプリケーションが閉じられる際の処理"""
        reply = QMessageBox.question(
            self, '確認', 'アプリケーションを終了しますか？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            logger.info("アプリケーションを終了します")
            event.accept()
        else:
            event.ignore() 
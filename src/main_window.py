import os
import sys
import logging
import time
from typing import List, Dict, Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QLineEdit, QPushButton, QProgressBar,
    QScrollArea, QGridLayout, QCheckBox, QMessageBox,
    QTextEdit, QGroupBox, QStatusBar, QSizePolicy, QFrame,
    QApplication, QSpacerItem, QTabWidget, QToolButton, QButtonGroup, QRadioButton, QStyle
)
from PyQt6.QtCore import Qt, QSize, QThreadPool, QRunnable, pyqtSignal, QObject, pyqtSlot, QMargins
from PyQt6.QtGui import QPixmap, QImage, QIcon, QFont, QColor, QPalette, QCursor, QGuiApplication, QPainter, QBrush, QPen, QLinearGradient, QGradient

from src.config_manager import get_settings
from src.hpb_scraper import get_salon_name, fetch_latest_style_images, download_images
from src.gbp_uploader import check_login, login_to_google, manual_login, upload_to_gbp

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
    
    # UI更新用のシグナルを追加
    update_log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        
        # アプリケーションのスタイル設定
        self.setup_application_style()
        
        self.threadpool = QThreadPool()
        logger.debug(f"利用可能なスレッド数: {self.threadpool.maxThreadCount()}")
        
        self.salon_name = ""  # サロン名を保存
        self.image_paths = []  # ダウンロードした画像のパスを保存
        self.image_checkboxes = []  # 画像のチェックボックスを保存
        
        self.init_ui()
        
        # シグナルとスロットを接続
        self.update_log_signal.connect(self._append_log_text)
    
    def setup_application_style(self):
        """アプリケーション全体のスタイル設定"""
        # カラーパレット
        self.palette = {
            'primary': '#4285F4',       # Google青
            'primary_dark': '#3367d6',  # Google青の暗い色
            'secondary': '#34A853',     # Google緑
            'secondary_dark': '#2e8b46', # Google緑の暗い色
            'accent': '#EA4335',        # Google赤
            'neutral': '#FBBC05',       # Google黄
            'background': '#f5f5f5',    # 背景色（明るいグレー）
            'card_bg': '#ffffff',       # カード背景色
            'card_border': '#e0e0e0',   # カード枠線色
            'text': '#202124',          # テキスト色（ダークグレー）
            'light_text': '#5f6368',    # 薄いテキスト色
            'border': '#dadce0',        # ボーダー色
            'card': '#ffffff',          # カード背景色
            'disabled': '#bdc1c6',      # 無効状態色
            'success': '#34A853',       # 成功色
            'error': '#EA4335',         # エラー色
            'warning': '#FBBC05'        # 警告色
        }
        
        # デバイスのピクセル比を取得してHiDPI対応
        pixel_ratio = QGuiApplication.primaryScreen().devicePixelRatio()
        
        # 基本フォント設定
        app_font = QFont("Hiragino Sans", 10)
        QApplication.setFont(app_font)
        
        # ウィンドウスタイル
        self.setWindowTitle("HotPepper Beauty 画像投稿ツール")
        self.setMinimumSize(1000, 700)  # ウィンドウサイズを大きく
        
        # ステータスバーのスタイル設定
        status_font = QFont("Hiragino Sans", 9)
        self.statusBar().setFont(status_font)
        
        # グローバルスタイルシート
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {self.palette['background']};
            }}
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {self.palette['border']};
                border-radius: 8px;
                margin-top: 1.5ex;
                padding: 12px;
                background-color: {self.palette['card']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 8px;
                color: {self.palette['text']};
                font-size: 13px;
                background-color: {self.palette['card']};
            }}
            QPushButton {{
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                background-color: {self.palette['card']};
                color: {self.palette['text']};
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #e8eaed;
            }}
            QPushButton:pressed {{
                background-color: #dadce0;
            }}
            QPushButton:disabled {{
                color: {self.palette['disabled']};
                background-color: #f1f3f4;
            }}
            QLineEdit {{
                border: 1px solid {self.palette['border']};
                border-radius: 4px;
                padding: 8px;
                background-color: white;
                selection-background-color: {self.palette['primary']};
                min-height: 20px;
            }}
            QLineEdit:focus {{
                border: 2px solid {self.palette['primary']};
            }}
            QLabel {{
                color: {self.palette['text']};
            }}
            QProgressBar {{
                border: none;
                border-radius: 4px;
                text-align: center;
                background-color: #e0e0e0;
                min-height: 6px;
                max-height: 6px;
            }}
            QProgressBar::chunk {{
                background-color: {self.palette['primary']};
                border-radius: 4px;
            }}
            QCheckBox {{
                spacing: 5px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 3px;
                border: 1px solid {self.palette['border']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {self.palette['primary']};
                border: none;
                image: url(:/qt-project.org/styles/commonstyle/images/check-white.png);
            }}
            QScrollArea {{
                border: 1px solid {self.palette['border']};
                border-radius: 8px;
                background-color: white;
            }}
            QScrollBar:vertical {{
                border: none;
                background-color: #f1f3f4;
                width: 10px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background-color: #dadce0;
                border-radius: 5px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: #bdc1c6;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar:horizontal {{
                border: none;
                background-color: #f1f3f4;
                height: 10px;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background-color: #dadce0;
                border-radius: 5px;
                min-width: 20px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background-color: #bdc1c6;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
            QTextEdit {{
                border: 1px solid {self.palette['border']};
                border-radius: 8px;
                background-color: white;
                selection-background-color: {self.palette['primary']};
                padding: 5px;
            }}
            QFrame {{
                border-radius: 8px;
            }}
        """)
        
        # アイコンの設定
        self.icons = {
            'fetch': self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
            'upload': self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp),
            'login': self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton),
            'manual_login': self.style().standardIcon(QStyle.StandardPixmap.SP_DialogHelpButton),
            'select_all': self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton),
            'deselect_all': self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton)
        }
    
    def init_ui(self):
        """UIの初期化"""
        # メインウィジェットとレイアウト
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)  # 余白を追加
        main_layout.setSpacing(12)  # ウィジェット間の間隔を設定
        self.setCentralWidget(main_widget)
        
        # タイトルラベル
        title_label = QLabel("HotPepper Beauty スタイル画像 GoogleMap自動投稿ツール")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet(f"""
            font-size: 18px;
            font-weight: bold;
            color: {self.palette['primary']};
            margin-bottom: 10px;
        """)
        main_layout.addWidget(title_label)
        
        # --- URL入力セクション ---
        url_group = QGroupBox("URL設定")
        url_layout = QVBoxLayout(url_group)
        url_layout.setContentsMargins(15, 15, 15, 15)
        url_layout.setSpacing(10)
        
        # HPB URL入力
        hpb_layout = QHBoxLayout()
        hpb_label = QLabel("HPB URL:")
        hpb_label.setMinimumWidth(80)
        hpb_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.hpb_url_input = QLineEdit()
        self.hpb_url_input.setPlaceholderText("https://beauty.hotpepper.jp/slnH000xxxxxx/")
        self.salon_name_label = QLabel("")
        self.salon_name_label.setStyleSheet(f"color: {self.palette['secondary']}; font-weight: bold;")
        hpb_layout.addWidget(hpb_label)
        hpb_layout.addWidget(self.hpb_url_input, 1)
        hpb_layout.addWidget(self.salon_name_label)
        
        main_layout.addLayout(hpb_layout)

        # --- Fetch Order Options (Radio Buttons) ---
        order_layout = QHBoxLayout()
        order_group_box = QGroupBox("画像取得順序")
        order_group_layout = QHBoxLayout(order_group_box)
        
        self.order_group = QButtonGroup(self)
        self.order_forward_radio = QRadioButton("最初のページから取得")
        self.order_backward_radio = QRadioButton("最後のページから取得")
        self.order_backward_radio.setChecked(True) # デフォルトは最後から
        
        self.order_group.addButton(self.order_forward_radio, 0) # ID 0 for forward
        self.order_group.addButton(self.order_backward_radio, 1) # ID 1 for backward
        
        order_group_layout.addWidget(self.order_forward_radio)
        order_group_layout.addWidget(self.order_backward_radio)
        order_group_layout.addStretch()
        
        order_layout.addWidget(order_group_box)
        main_layout.addLayout(order_layout)

        # --- GBP URL Input ---
        gbp_layout = QHBoxLayout()
        gbp_label = QLabel("GBP URL:")
        gbp_label.setMinimumWidth(80)
        gbp_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.gbp_url_input = QLineEdit()
        self.gbp_url_input.setPlaceholderText("https://www.google.com/")
        gbp_layout.addWidget(gbp_label)
        gbp_layout.addWidget(self.gbp_url_input, 1)
        
        url_layout.addLayout(gbp_layout)
        
        main_layout.addWidget(url_group)
        
        # --- 上部操作ボタンセクション ---
        top_button_container = QWidget()
        top_button_container.setStyleSheet(f"""
            background-color: transparent;
            margin: 0;
            padding: 0;
        """)
        top_button_layout = QHBoxLayout(top_button_container)
        top_button_layout.setContentsMargins(0, 5, 0, 5)
        top_button_layout.setSpacing(15)
        
        # メイン操作ボタンセクション（左側）
        main_buttons_widget = QWidget()
        main_buttons_layout = QHBoxLayout(main_buttons_widget)
        main_buttons_layout.setContentsMargins(0, 0, 0, 0)
        main_buttons_layout.setSpacing(12)
        
        # 画像取得ボタン（強調表示）
        self.fetch_button = QPushButton("  画像を取得")
        self.fetch_button.setIcon(self.icons['fetch'])
        self.fetch_button.setIconSize(QSize(18, 18))
        self.fetch_button.setStyleSheet(f"""
            background-color: {self.palette['primary']};
            color: white;
            font-size: 14px;
            font-weight: bold;
            min-height: 40px;
            padding: 0 20px;
            border-radius: 6px;
            text-align: left;
        """)
        self.fetch_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.fetch_button.clicked.connect(self.fetch_images)
        main_buttons_layout.addWidget(self.fetch_button)
        
        # 選択した画像を投稿ボタン（強調表示）
        self.upload_button = QPushButton("  選択した画像を投稿")
        self.upload_button.setIcon(self.icons['upload'])
        self.upload_button.setIconSize(QSize(18, 18))
        self.upload_button.setStyleSheet(f"""
            background-color: {self.palette['secondary']};
            color: white;
            font-size: 14px;
            font-weight: bold;
            min-height: 40px;
            padding: 0 20px;
            border-radius: 6px;
            text-align: left;
        """)
        self.upload_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.upload_button.clicked.connect(self.upload_selected_images)
        self.upload_button.setEnabled(False)
        main_buttons_layout.addWidget(self.upload_button)
        
        # ログインボタンセクション（右側）
        login_buttons_widget = QWidget()
        login_buttons_layout = QHBoxLayout(login_buttons_widget)
        login_buttons_layout.setContentsMargins(0, 0, 0, 0)
        login_buttons_layout.setSpacing(8)
        
        # Googleログインボタン
        self.login_button = QPushButton("  Googleログイン確認")
        self.login_button.setIcon(self.icons['login'])
        self.login_button.setIconSize(QSize(16, 16))
        self.login_button.setStyleSheet(f"""
            background-color: white;
            border: 1px solid {self.palette['border']};
            border-radius: 6px;
            min-height: 36px;
            text-align: left;
        """)
        self.login_button.clicked.connect(self.check_google_login)
        login_buttons_layout.addWidget(self.login_button)
        
        # 手動Googleログインボタン
        self.manual_login_button = QPushButton("  手動Googleログイン")
        self.manual_login_button.setIcon(self.icons['manual_login'])
        self.manual_login_button.setIconSize(QSize(16, 16))
        self.manual_login_button.setStyleSheet(f"""
            background-color: white;
            border: 1px solid {self.palette['border']};
            border-radius: 6px;
            min-height: 36px;
            text-align: left;
        """)
        self.manual_login_button.clicked.connect(self.perform_manual_google_login)
        login_buttons_layout.addWidget(self.manual_login_button)
        
        # レイアウトに追加
        top_button_layout.addWidget(main_buttons_widget, 2)  # メインボタンを広く
        top_button_layout.addWidget(login_buttons_widget, 1)  # ログインボタンを狭く
        
        main_layout.addWidget(top_button_container)
        
        # --- 画像表示セクション ---
        images_group = QGroupBox("ヘアスタイル画像")
        images_layout = QVBoxLayout(images_group)
        images_layout.setContentsMargins(10, 20, 10, 10)
        images_layout.setSpacing(10)
        
        # 全選択/全解除ボタン
        select_buttons_layout = QHBoxLayout()
        select_buttons_layout.setContentsMargins(5, 0, 5, 10)
        
        select_label = QLabel("画像選択:")
        select_label.setStyleSheet("font-weight: bold;")
        select_buttons_layout.addWidget(select_label)
        
        self.select_all_button = QPushButton("  全て選択")
        self.select_all_button.setIcon(self.icons['select_all'])
        self.select_all_button.setIconSize(QSize(16, 16))
        self.select_all_button.setStyleSheet(f"""
            max-width: 120px;
            padding: 5px 8px;
            background-color: {self.palette['primary']};
            color: white;
            border-radius: 4px;
            text-align: left;
        """)
        self.select_all_button.clicked.connect(self.select_all_images)
        self.select_all_button.setEnabled(False)
        select_buttons_layout.addWidget(self.select_all_button)
        
        self.deselect_all_button = QPushButton("  全て解除")
        self.deselect_all_button.setIcon(self.icons['deselect_all'])
        self.deselect_all_button.setIconSize(QSize(16, 16))
        self.deselect_all_button.setStyleSheet(f"""
            max-width: 120px;
            padding: 5px 8px;
            background-color: #f1f3f4;
            color: {self.palette['text']};
            border: 1px solid {self.palette['border']};
            border-radius: 4px;
            text-align: left;
        """)
        self.deselect_all_button.clicked.connect(self.deselect_all_images)
        self.deselect_all_button.setEnabled(False)
        select_buttons_layout.addWidget(self.deselect_all_button)
        
        select_buttons_layout.addStretch()
        images_layout.addLayout(select_buttons_layout)
        
        # スクロール可能な画像グリッドエリア
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(300)  # 最低限の高さを確保
        scroll_content = QWidget()
        scroll_content.setStyleSheet(f"background-color: white;")
        
        self.images_grid = QGridLayout(scroll_content)
        self.images_grid.setContentsMargins(10, 10, 10, 10)
        self.images_grid.setSpacing(15)  # グリッド内の間隔を広げる
        
        scroll_area.setWidget(scroll_content)
        images_layout.addWidget(scroll_area)
        
        main_layout.addWidget(images_group, 1)  # 画像表示セクションに伸縮性を持たせる
        
        # --- ステータス表示セクション ---
        status_group = QGroupBox("進捗状況")
        status_group.setStyleSheet(f"""
            QGroupBox {{
                border: 1px solid {self.palette['border']};
                border-radius: 8px;
                margin-top: 1.5ex;
                padding: 12px;
                background-color: {self.palette['card']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 8px;
                color: {self.palette['primary']};
                font-size: 13px;
                font-weight: bold;
                background-color: {self.palette['card']};
            }}
        """)
        status_layout = QVBoxLayout(status_group)
        status_layout.setContentsMargins(15, 20, 15, 15)
        status_layout.setSpacing(12)
        
        # プログレスバー
        progress_layout = QHBoxLayout()
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(10)
        
        progress_label = QLabel("処理状況:")
        progress_label.setMinimumWidth(70)
        progress_label.setStyleSheet(f"color: {self.palette['text']}; font-weight: bold;")
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                border-radius: 4px;
                background-color: #e0e0e0;
                color: {self.palette['text']};
                font-weight: bold;
                min-height: 20px;
                max-height: 20px;
            }}
            QProgressBar::chunk {{
                background-color: {self.palette['primary']};
                border-radius: 4px;
            }}
        """)
        
        progress_layout.addWidget(progress_label)
        progress_layout.addWidget(self.progress_bar)
        status_layout.addLayout(progress_layout)
        
        # ログテキストエリア
        log_layout = QVBoxLayout()
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(8)
        
        log_label = QLabel("処理ログ:")
        log_label.setStyleSheet(f"color: {self.palette['text']}; font-weight: bold;")
        log_layout.addWidget(log_label)
        
        log_frame = QFrame()
        log_frame.setStyleSheet(f"""
            background-color: white;
            border: 1px solid {self.palette['border']};
            border-radius: 6px;
        """)
        log_frame_layout = QVBoxLayout(log_frame)
        log_frame_layout.setContentsMargins(10, 10, 10, 10)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(120)
        self.log_text.setStyleSheet("""
            border: none;
            background-color: white;
            font-family: Menlo, Monaco, Consolas, "Courier New", monospace;
            font-size: 11px;
            line-height: 1.5;
            padding: 0;
        """)
        log_frame_layout.addWidget(self.log_text)
        
        log_layout.addWidget(log_frame)
        status_layout.addLayout(log_layout)
        
        main_layout.addWidget(status_group)
        
        # ステータスバー
        self.statusBar().showMessage("準備完了")
        self.statusBar().setStyleSheet(f"""
            background-color: {self.palette['background']};
            border-top: 1px solid {self.palette['border']};
            padding: 3px;
        """)
        
        # UIの初期化が完了したことをログに記録
        self.log_message("アプリケーションの準備が完了しました。")
    
    @pyqtSlot(str)
    def _append_log_text(self, message: str):
        """メインスレッドでログテキストエリアにメッセージを追加するスロット"""
        self.log_text.append(message)
    
    def log_message(self, message: str):
        """ログメッセージをシグナル経由で表示エリアに追加"""
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        formatted_message = f"[{timestamp}] {message}"
        # 直接UIを更新せず、シグナルを発行する
        self.update_log_signal.emit(formatted_message)
        logger.info(message) # ロガーへの出力はスレッドセーフ
    
    def check_google_login(self):
        """Googleログイン状態をチェック"""
        self.log_message("Googleログイン状態を確認中...")
        self.login_button.setEnabled(False)
        self.statusBar().showMessage("Googleログイン状態を確認中...")
        
        # Googleログイン状態をチェックするワーカーを作成
        worker = Worker(check_login)
        worker.signals.result.connect(self.on_login_check_result)
        worker.signals.error.connect(self.on_worker_error)
        worker.signals.finished.connect(lambda: self.login_button.setEnabled(True))
        self.threadpool.start(worker)
    
    def on_login_check_result(self, is_logged_in):
        """ログイン状態チェック結果の処理"""
        if is_logged_in:
            self.log_message("Googleにログイン済みです")
            self.statusBar().showMessage("Googleにログイン済み")
            
            # ログイン状態を視覚的に表示
            self.login_button.setStyleSheet(f"""
                background-color: {self.palette['success']};
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                min-height: 36px;
                text-align: left;
            """)
            
            QMessageBox.information(self, "ログイン状態", "Googleにログイン済みです。画像投稿が可能です。")
        else:
            self.log_message("Googleにログインが必要です")
            self.statusBar().showMessage("Googleにログインが必要です")
            
            # 未ログイン状態を視覚的に表示
            self.login_button.setStyleSheet(f"""
                background-color: {self.palette['error']};
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                min-height: 36px;
                text-align: left;
            """)
            
            reply = QMessageBox.question(
                self, 'ログイン', 'Googleにログインが必要です。ログインを実行しますか？',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.perform_google_login()
    
    def perform_google_login(self):
        """Google ログインを実行"""
        self.log_message("Googleログインプロセスを開始します")
        self.login_button.setEnabled(False)
        self.statusBar().showMessage("Googleログイン中...")
        
        def progress_callback(message):
            self.log_message(message)
        
        # Googleログインを実行するワーカーを作成
        worker = Worker(login_to_google, progress_callback)
        worker.signals.result.connect(self.on_login_result)
        worker.signals.error.connect(self.on_worker_error)
        worker.signals.finished.connect(lambda: self.login_button.setEnabled(True))
        self.threadpool.start(worker)
    
    def on_login_result(self, login_success):
        """ログイン結果の処理"""
        if login_success:
            self.log_message("Googleログインが完了しました")
            self.statusBar().showMessage("Googleログイン完了")
            
            # ログイン成功状態を視覚的に表示
            self.login_button.setStyleSheet(f"""
                background-color: {self.palette['success']};
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                min-height: 36px;
                text-align: left;
            """)
            
            QMessageBox.information(self, "ログイン完了", "Googleログインが完了しました。画像投稿が可能です。")
        else:
            self.log_message("Googleログインに失敗しました")
            self.statusBar().showMessage("Googleログイン失敗")
            
            # ログイン失敗状態を視覚的に表示
            self.login_button.setStyleSheet(f"""
                background-color: {self.palette['error']};
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                min-height: 36px;
                text-align: left;
            """)
            
            QMessageBox.warning(self, "ログイン失敗", "Googleログインに失敗しました。もう一度試すか、手動でログインしてください。")
    
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
        
        # ボタンのスタイルを変更して無効状態を視覚的に表示
        self.fetch_button.setStyleSheet(f"""
            background-color: {self.palette['disabled']};
            color: white;
            font-size: 14px;
            font-weight: bold;
            min-height: 40px;
            padding: 0 20px;
            border-radius: 6px;
            text-align: left;
        """)
        
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
            
            # 選択された取得順序を取得
            if self.order_forward_radio.isChecked():
                fetch_order = 'forward'
            else: # backward is default
                fetch_order = 'backward'
            self.log_message(f"取得順序: {'最初のページから' if fetch_order == 'forward' else '最後のページから'}")
            
            # Worker に order 引数を渡す
            worker = Worker(fetch_latest_style_images, hpb_url, order=fetch_order)
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
            
            # 画像ダウンロード進捗ログ用コールバック関数
            def download_progress_callback(message):
                self.log_message(message)
            
            # Step 3: 画像をダウンロード
            worker = Worker(download_images, image_urls, progress_callback=download_progress_callback)
            worker.signals.result.connect(self.on_images_downloaded)
            worker.signals.error.connect(self.on_worker_error)
            worker.signals.finished.connect(lambda: self.progress_bar.setValue(100))
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
            
            # ボタンスタイルを元に戻す
            self.fetch_button.setStyleSheet(f"""
                background-color: {self.palette['primary']};
                color: white;
                font-size: 14px;
                font-weight: bold;
                min-height: 40px;
                padding: 0 20px;
                border-radius: 6px;
                text-align: left;
            """)
            
            # 成功メッセージを表示
            QMessageBox.information(
                self, 
                "画像取得完了", 
                f"{len(image_paths)}件の画像を取得しました。\n投稿する画像を選択してください。"
            )
            
        else:
            self.log_message("画像のダウンロードに失敗しました")
            self.fetch_button.setEnabled(True)
            
            # ボタンスタイルを元に戻す
            self.fetch_button.setStyleSheet(f"""
                background-color: {self.palette['primary']};
                color: white;
                font-size: 14px;
                font-weight: bold;
                min-height: 40px;
                padding: 0 20px;
                border-radius: 6px;
                text-align: left;
            """)
            
            self.statusBar().showMessage("画像のダウンロードに失敗しました")
        
        self.fetch_button.setEnabled(True)
    
    def display_images(self, image_paths: List[str]):
        """ダウンロードした画像を表示エリアに表示"""
        # 既存の画像とチェックボックスをクリア
        for i in reversed(range(self.images_grid.count())): 
            self.images_grid.itemAt(i).widget().setParent(None)
        self.image_checkboxes.clear()
        
        # サムネイルサイズ - 大きく表示
        thumbnail_size = 200
        
        # グリッド内の列数を計算（ウィンドウサイズに応じて調整）
        grid_columns = max(3, min(5, self.width() // 250))
        
        # 画像をグリッドで表示
        for idx, image_path in enumerate(image_paths):
            row, col = divmod(idx, grid_columns)
            
            # 画像フレーム
            frame = QFrame()
            frame.setStyleSheet(f"""
                border: 1px solid {self.palette['card_border']};
                border-radius: 10px;
                background-color: white;
                margin: 8px;
            """)
            
            # 影をつけるのは難しいので、より洗練された枠線効果を適用
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(0, 0, 0, 0)
            frame_layout.setSpacing(0)
            
            # 画像コンテナ（上部）
            image_container = QWidget()
            image_container.setFixedHeight(thumbnail_size + 20)
            image_container.setStyleSheet(f"""
                background-color: white;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                border-bottom: 1px solid {self.palette['card_border']};
            """)
            
            image_container_layout = QVBoxLayout(image_container)
            image_container_layout.setContentsMargins(10, 10, 10, 10)
            image_container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # 画像のロードと表示
            pixmap = QPixmap(image_path)
            scaled_pixmap = pixmap.scaled(
                thumbnail_size, thumbnail_size, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            
            image_label = QLabel()
            image_label.setPixmap(scaled_pixmap)
            image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            image_label.setStyleSheet("""
                border: none;
                background-color: transparent;
            """)
            image_container_layout.addWidget(image_label)
            frame_layout.addWidget(image_container)
            
            # 情報コンテナ（下部）
            info_container = QWidget()
            info_container.setStyleSheet(f"""
                background-color: #f8f9fa;
                border-bottom-left-radius: 10px;
                border-bottom-right-radius: 10px;
                padding: 5px;
            """)
            
            info_layout = QVBoxLayout(info_container)
            info_layout.setContentsMargins(10, 8, 10, 8)
            info_layout.setSpacing(6)
            
            # ファイル名表示（省略表示）
            filename = os.path.basename(image_path)
            if len(filename) > 20:
                # ファイル名が長い場合は省略
                display_name = filename[:10] + "..." + filename[-7:]
            else:
                display_name = filename
                
            name_label = QLabel(display_name)
            name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_label.setStyleSheet(f"""
                color: {self.palette['text']};
                font-size: 11px;
                font-weight: bold;
                padding: 2px;
            """)
            name_label.setToolTip(filename)  # 完全なファイル名をツールチップで表示
            info_layout.addWidget(name_label)
            
            # チェックボックス（デフォルトで選択済み）
            checkbox_container = QWidget()
            checkbox_container.setStyleSheet("background-color: transparent;")
            checkbox_layout = QHBoxLayout(checkbox_container)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            checkbox = QCheckBox("選択する")
            checkbox.setChecked(True)
            checkbox.setProperty("image_path", image_path)
            checkbox.setStyleSheet(f"""
                font-size: 12px;
                color: {self.palette['text']};
                spacing: 5px;
            """)
            self.image_checkboxes.append(checkbox)
            checkbox_layout.addWidget(checkbox)
            
            info_layout.addWidget(checkbox_container)
            frame_layout.addWidget(info_container)
            
            self.images_grid.addWidget(frame, row, col)
        
        # 画像枠の最小幅を設定して見切れを防止
        for col in range(grid_columns):
            self.images_grid.setColumnMinimumWidth(col, thumbnail_size + 40)
    
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
        
        # ログイン状態を確認
        check_worker = Worker(check_login)
        check_worker.signals.result.connect(lambda logged_in: self.proceed_with_upload(logged_in, gbp_url, selected_paths))
        check_worker.signals.error.connect(self.on_worker_error)
        check_worker.signals.finished.connect(lambda: self.upload_button.setEnabled(True))
        self.threadpool.start(check_worker)
    
    def proceed_with_upload(self, is_logged_in, gbp_url, selected_paths):
        """ログイン状態に応じてアップロードを続行するかログインを促す"""
        if not is_logged_in:
            reply = QMessageBox.question(
                self, 'ログイン必要', 'Googleにログインが必要です。ログインを実行しますか？',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.perform_google_login()
            return
        
        # アップロード実行
        self.upload_button.setEnabled(False)
        
        # ボタンのスタイルを変更して処理中状態を視覚的に表示
        self.upload_button.setStyleSheet(f"""
            background-color: {self.palette['disabled']};
            color: white;
            font-size: 14px;
            font-weight: bold;
            min-height: 40px;
            padding: 0 20px;
            border-radius: 6px;
            text-align: left;
        """)
        
        self.statusBar().showMessage("GBPに画像をアップロード中...")
        self.progress_bar.setValue(0)
        
        def progress_callback(message):
            self.log_message(message)
            
        # GBP投稿ワーカーを作成
        upload_worker = Worker(upload_to_gbp, gbp_url, selected_paths, progress_callback)
        upload_worker.signals.result.connect(self.on_upload_result)
        upload_worker.signals.error.connect(self.on_worker_error)
        upload_worker.signals.finished.connect(lambda: self.upload_button.setEnabled(True))
        self.threadpool.start(upload_worker)
    
    def on_upload_result(self, upload_success):
        """アップロード結果の処理"""
        if upload_success:
            self.log_message("画像の投稿が完了しました")
            self.statusBar().showMessage("画像投稿完了")
            self.progress_bar.setValue(100)
            
            # ボタンスタイルを元に戻す
            self.upload_button.setStyleSheet(f"""
                background-color: {self.palette['secondary']};
                color: white;
                font-size: 14px;
                font-weight: bold;
                min-height: 40px;
                padding: 0 20px;
                border-radius: 6px;
                text-align: left;
            """)
            
            QMessageBox.information(self, "投稿完了", "画像の投稿が完了しました。")
        else:
            self.log_message("画像の投稿に失敗しました")
            self.statusBar().showMessage("画像投稿失敗")
            
            # ボタンスタイルを元に戻す
            self.upload_button.setStyleSheet(f"""
                background-color: {self.palette['secondary']};
                color: white;
                font-size: 14px;
                font-weight: bold;
                min-height: 40px;
                padding: 0 20px;
                border-radius: 6px;
                text-align: left;
            """)
            
            QMessageBox.warning(self, "投稿失敗", "画像の投稿に失敗しました。ログイン状態とGBP URLを確認してください。")
    
    def on_worker_error(self, error_msg):
        """ワーカースレッドでエラーが発生した場合の処理"""
        self.log_message(f"エラーが発生しました: {error_msg}")
        self.statusBar().showMessage("エラーが発生しました")
        
        # ボタンスタイルを元に戻す
        self.fetch_button.setStyleSheet(f"""
            background-color: {self.palette['primary']};
            color: white;
            font-size: 14px;
            font-weight: bold;
            min-height: 40px;
            padding: 0 20px;
            border-radius: 6px;
            text-align: left;
        """)
        
        self.upload_button.setStyleSheet(f"""
            background-color: {self.palette['secondary']};
            color: white;
            font-size: 14px;
            font-weight: bold;
            min-height: 40px;
            padding: 0 20px;
            border-radius: 6px;
            text-align: left;
        """)
        
        self.fetch_button.setEnabled(True)
        
    def perform_manual_google_login(self):
        """Google手動ログインを実行"""
        self.log_message("Google手動ログインプロセスを開始します")
        self.manual_login_button.setEnabled(False)
        self.statusBar().showMessage("Google手動ログイン中...")
        
        def progress_callback(message):
            self.log_message(message)
        
        # Google手動ログインを実行するワーカーを作成
        worker = Worker(manual_login, progress_callback)
        worker.signals.result.connect(self.on_manual_login_result)
        worker.signals.error.connect(self.on_worker_error)
        worker.signals.finished.connect(lambda: self.manual_login_button.setEnabled(True))
        self.threadpool.start(worker)
    
    def on_manual_login_result(self, login_success):
        """手動ログイン結果の処理"""
        if login_success:
            self.log_message("Google手動ログインが完了しました")
            self.statusBar().showMessage("Google手動ログイン完了")
            
            # ログイン成功状態を視覚的に表示
            self.login_button.setStyleSheet(f"""
                background-color: {self.palette['success']};
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                min-height: 36px;
                text-align: left;
            """)
            
            QMessageBox.information(self, "ログイン完了", "Google手動ログインが完了しました。画像投稿が可能です。")
        else:
            self.log_message("Google手動ログインに失敗しました")
            self.statusBar().showMessage("Google手動ログイン失敗")
            
            # ログイン失敗状態を視覚的に表示
            self.login_button.setStyleSheet(f"""
                background-color: {self.palette['error']};
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                min-height: 36px;
                text-align: left;
            """)
            
            QMessageBox.warning(self, "ログイン失敗", "Google手動ログインに失敗しました。もう一度試すか、別の方法でログインしてください。")
    
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
"""
サムネイルグリッドウィジェット
画像をグリッド表示し、選択可能にする
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Literal, Optional

from PySide6.QtCore import Qt, Signal, QThreadPool, QRunnable, Slot, QObject
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QGridLayout, QPushButton, QFrame, QComboBox
)

from services.thumbnail_cache import ThumbnailCache
from services.exif import ExifReader
from utils.pathsafe import is_image_file

logger = logging.getLogger(__name__)


class ThumbnailSignals(QObject):
    """サムネイル読み込み用のシグナル"""
    loaded = Signal(str, QPixmap, str)  # path, pixmap, datetime_str


class ThumbnailLoader(QRunnable):
    """サムネイルをバックグラウンドで読み込むワーカー"""

    def __init__(self, file_path: str, cache: ThumbnailCache, size=(200, 200)):
        super().__init__()
        self.file_path = file_path
        self.cache = cache
        self.size = size
        self.signals = ThumbnailSignals()

    @Slot()
    def run(self):
        """バックグラウンド処理"""
        try:
            # サムネイル生成
            pixmap = self.cache.get(self.file_path, self.size)

            # EXIF情報取得
            dt = ExifReader.read_datetime(self.file_path)
            dt_str = dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""

            # シグナル発火
            if pixmap:
                self.signals.loaded.emit(self.file_path, pixmap, dt_str)

        except Exception as e:
            logger.error(f"サムネイル読み込みエラー ({self.file_path}): {e}")


class ThumbnailItem(QFrame):
    """個別のサムネイルアイテム"""

    clicked = Signal(str)  # file_path

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.is_selected = False

        self._setup_ui()

    def _setup_ui(self):
        """UIセットアップ"""
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        self.setLineWidth(2)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # レイアウト
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # サムネイル画像
        self.image_label = QLabel()
        self.image_label.setFixedSize(200, 200)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: #f0f0f0;")
        self.image_label.setText("読み込み中...")
        layout.addWidget(self.image_label)

        # ファイル名
        self.name_label = QLabel(Path(self.file_path).name)
        self.name_label.setWordWrap(True)
        self.name_label.setMaximumWidth(200)
        self.name_label.setStyleSheet("font-size: 10px;")
        layout.addWidget(self.name_label)

        # 撮影日時
        self.datetime_label = QLabel("")
        self.datetime_label.setStyleSheet("font-size: 9px; color: #666;")
        layout.addWidget(self.datetime_label)

        self.setMaximumWidth(220)

    def set_thumbnail(self, pixmap: QPixmap, datetime_str: str):
        """サムネイルをセット"""
        self.image_label.setPixmap(pixmap.scaled(
            200, 200,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))
        if datetime_str:
            self.datetime_label.setText(datetime_str)

    def set_selected(self, selected: bool):
        """選択状態を設定"""
        self.is_selected = selected
        if selected:
            self.setStyleSheet("ThumbnailItem { border: 3px solid #2196F3; background-color: #E3F2FD; }")
        else:
            self.setStyleSheet("ThumbnailItem { border: 1px solid #ccc; }")

    def mousePressEvent(self, event):
        """マウスクリックイベント"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.file_path)
        super().mousePressEvent(event)


class ThumbnailGrid(QWidget):
    """サムネイルをグリッド表示するウィジェット"""

    image_clicked = Signal(str)  # file_path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cache = ThumbnailCache(max_cache_size=500)
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(4)  # 同時読み込み数

        self.image_files: List[str] = []
        self.thumbnail_items: dict[str, ThumbnailItem] = {}
        self.selected_paths: set[str] = set()

        self._setup_ui()

    def _setup_ui(self):
        """UIセットアップ"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 上部：並び替えコントロール
        control_layout = QHBoxLayout()

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["撮影日時（昇順）", "撮影日時（降順）", "ファイル名"])
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        control_layout.addWidget(QLabel("並び替え:"))
        control_layout.addWidget(self.sort_combo)
        control_layout.addStretch()

        layout.addLayout(control_layout)

        # スクロールエリア
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # グリッドコンテナ
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(10)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        scroll_area.setWidget(self.grid_widget)
        layout.addWidget(scroll_area)

    def load_folder(self, folder_path: str):
        """
        フォルダを読み込んでサムネイル表示

        Args:
            folder_path: フォルダパス
        """
        folder = Path(folder_path)
        if not folder.is_dir():
            logger.warning(f"ディレクトリではありません: {folder_path}")
            return

        # 既存のアイテムをクリア
        self.clear()

        # 画像ファイルを収集
        self.image_files = []
        for file_path in folder.iterdir():
            if file_path.is_file() and is_image_file(file_path):
                self.image_files.append(str(file_path))

        logger.info(f"{len(self.image_files)}個の画像ファイルを検出")

        # ソートモードを適用
        self._apply_sort()

    def _apply_sort(self):
        """現在のソートモードを適用"""
        sort_mode = self.sort_combo.currentIndex()

        if sort_mode == 0:  # 撮影日時（昇順）
            self.set_sort("exif_asc")
        elif sort_mode == 1:  # 撮影日時（降順）
            self.set_sort("exif_desc")
        else:  # ファイル名
            self.set_sort("name")

    def set_sort(self, mode: Literal["exif_asc", "exif_desc", "name"]):
        """
        並び替えモードを設定

        Args:
            mode: ソートモード
        """
        if mode == "name":
            # ファイル名でソート
            self.image_files.sort(key=lambda p: Path(p).name)
        elif mode in ["exif_asc", "exif_desc"]:
            # EXIF日時でソート（重い処理なのでログ出力）
            logger.info("EXIF情報を読み込み中...")

            # 日時情報を取得
            files_with_datetime = []
            for file_path in self.image_files:
                dt = ExifReader.read_datetime(file_path)
                files_with_datetime.append((file_path, dt or datetime.min))

            # ソート
            reverse = (mode == "exif_desc")
            files_with_datetime.sort(key=lambda x: x[1], reverse=reverse)
            self.image_files = [f[0] for f in files_with_datetime]

        # グリッドを再構築
        self._rebuild_grid()

    def _rebuild_grid(self):
        """グリッドを再構築"""
        # 既存のアイテムを削除
        for item in self.thumbnail_items.values():
            self.grid_layout.removeWidget(item)
            item.deleteLater()
        self.thumbnail_items.clear()

        # 新しいアイテムを追加
        columns = 4  # 1行あたりのカラム数
        for idx, file_path in enumerate(self.image_files):
            row = idx // columns
            col = idx % columns

            # サムネイルアイテム作成
            item = ThumbnailItem(file_path)
            item.clicked.connect(self._on_item_clicked)
            self.thumbnail_items[file_path] = item
            self.grid_layout.addWidget(item, row, col)

            # 選択状態を復元
            if file_path in self.selected_paths:
                item.set_selected(True)

            # バックグラウンドでサムネイル読み込み
            self._load_thumbnail_async(file_path)

    def _load_thumbnail_async(self, file_path: str):
        """サムネイルを非同期で読み込み"""
        loader = ThumbnailLoader(file_path, self.cache)
        loader.signals.loaded.connect(self._on_thumbnail_loaded)
        self.thread_pool.start(loader)

    @Slot(str, QPixmap, str)
    def _on_thumbnail_loaded(self, file_path: str, pixmap: QPixmap, datetime_str: str):
        """サムネイル読み込み完了時の処理"""
        if file_path in self.thumbnail_items:
            self.thumbnail_items[file_path].set_thumbnail(pixmap, datetime_str)

    def _on_item_clicked(self, file_path: str):
        """アイテムクリック時の処理"""
        # 選択状態をトグル
        if file_path in self.selected_paths:
            self.selected_paths.remove(file_path)
            if file_path in self.thumbnail_items:
                self.thumbnail_items[file_path].set_selected(False)
        else:
            self.selected_paths.add(file_path)
            if file_path in self.thumbnail_items:
                self.thumbnail_items[file_path].set_selected(True)

        # シグナル発火
        self.image_clicked.emit(file_path)

    def _on_sort_changed(self, index: int):
        """ソート変更時の処理"""
        self._apply_sort()

    def clear(self):
        """すべてのアイテムをクリア"""
        for item in self.thumbnail_items.values():
            self.grid_layout.removeWidget(item)
            item.deleteLater()

        self.thumbnail_items.clear()
        self.image_files.clear()
        self.selected_paths.clear()

    def get_selected_paths(self) -> List[str]:
        """選択されたパスのリストを取得"""
        return list(self.selected_paths)

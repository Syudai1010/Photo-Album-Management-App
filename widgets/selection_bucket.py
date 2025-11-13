"""
選択バスケットウィジェット
選択した画像を順序付きで管理し、ドラッグ&ドロップで並べ替え可能
"""
import logging
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QAbstractItemView, QLineEdit, QFrame
)

logger = logging.getLogger(__name__)


class SelectionItem:
    """選択アイテムのデータクラス"""

    def __init__(self, path: str, label: str = "全景", group: int = 1):
        self.path = path
        self.label = label
        self.group = group

    @property
    def name(self) -> str:
        """ファイル名を取得"""
        return Path(self.path).name

    def __repr__(self) -> str:
        return f"SelectionItem(path={self.path}, label={self.label}, group={self.group})"


class SelectionBucket(QWidget):
    """選択バスケットウィジェット"""

    items_changed = Signal()  # アイテムが変更された時
    label_applied = Signal(str)  # ラベルが適用された時（ラベル名）
    cleared = Signal()  # すべてクリアされた時

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: List[SelectionItem] = []
        self._selected_paths: set[str] = set()  # 選択中の画像パス
        self._setup_ui()

    def _setup_ui(self):
        """UIセットアップ"""
        layout = QVBoxLayout(self)

        # タイトル
        title_label = QLabel("選択バスケット（選んだ順）")
        title_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(title_label)

        # リストウィジェット（ドラッグ&ドロップ対応）
        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.model().rowsMoved.connect(self._on_rows_moved)
        layout.addWidget(self.list_widget)

        # コントロールボタン
        button_layout = QHBoxLayout()

        self.move_up_btn = QPushButton("▲ 上へ")
        self.move_up_btn.clicked.connect(self._move_up)
        button_layout.addWidget(self.move_up_btn)

        self.move_down_btn = QPushButton("▼ 下へ")
        self.move_down_btn.clicked.connect(self._move_down)
        button_layout.addWidget(self.move_down_btn)

        self.remove_btn = QPushButton("削除")
        self.remove_btn.clicked.connect(self._remove_selected)
        button_layout.addWidget(self.remove_btn)

        self.clear_btn = QPushButton("すべてクリア")
        self.clear_btn.clicked.connect(self.clear)
        button_layout.addWidget(self.clear_btn)

        layout.addLayout(button_layout)

        # ラベル一括設定
        label_layout = QHBoxLayout()
        label_layout.addWidget(QLabel("ラベル一括適用:"))

        self.label_input = QLineEdit()
        self.label_input.setPlaceholderText("全景")
        label_layout.addWidget(self.label_input)

        self.apply_label_btn = QPushButton("適用")
        self.apply_label_btn.clicked.connect(self._apply_label_to_all)
        label_layout.addWidget(self.apply_label_btn)

        layout.addLayout(label_layout)

        # カウント表示
        self.count_label = QLabel("選択数: 0")
        self.count_label.setStyleSheet("color: #666;")
        layout.addWidget(self.count_label)

    def add_item(self, path: str, label: str = "全景", group: int = 1):
        """
        アイテムを追加

        Args:
            path: ファイルパス
            label: ラベル
            group: グループ番号
        """
        # 既に存在する場合は削除
        self.remove_item(path)

        # 新しいアイテムを追加
        item = SelectionItem(path, label, group)
        self._items.append(item)

        # リストウィジェットに追加
        self._add_list_item(item)

        # カウント更新
        self._update_count()

        # シグナル発火
        self.items_changed.emit()

        logger.debug(f"アイテム追加: {path}")

    def remove_item(self, path: str):
        """
        アイテムを削除

        Args:
            path: ファイルパス
        """
        # _itemsから削除
        self._items = [item for item in self._items if item.path != path]

        # リストウィジェットから削除
        for i in range(self.list_widget.count()):
            list_item = self.list_widget.item(i)
            if list_item.data(Qt.ItemDataRole.UserRole) == path:
                self.list_widget.takeItem(i)
                break

        # カウント更新
        self._update_count()

        # シグナル発火
        self.items_changed.emit()

    def toggle_item(self, path: str, label: str = "全景", group: int = 1):
        """
        アイテムをトグル（存在すれば削除、なければ追加）

        Args:
            path: ファイルパス
            label: ラベル
            group: グループ番号
        """
        if self.has_item(path):
            self.remove_item(path)
        else:
            self.add_item(path, label, group)

    def has_item(self, path: str) -> bool:
        """
        アイテムが存在するかチェック

        Args:
            path: ファイルパス

        Returns:
            存在する場合True
        """
        return any(item.path == path for item in self._items)

    def clear(self):
        """すべてのアイテムをクリア"""
        self._items.clear()
        self.list_widget.clear()
        self._update_count()
        self.items_changed.emit()
        self.cleared.emit()  # クリアされたことを通知

    def items(self) -> List[SelectionItem]:
        """
        アイテムのリストを取得（現在の順序）

        Returns:
            SelectionItemのリスト
        """
        return self._items.copy()

    def get_items_dict(self) -> List[dict]:
        """
        アイテムを辞書形式で取得

        Returns:
            {'path': str, 'label': str, 'group': int} の形式のリスト
        """
        return [
            {'path': item.path, 'label': item.label, 'group': item.group}
            for item in self._items
        ]

    def _add_list_item(self, item: SelectionItem):
        """リストウィジェットにアイテムを追加"""
        display_text = f"{len(self._items)}. {item.name} [{item.label}]"

        list_item = QListWidgetItem(display_text)
        list_item.setData(Qt.ItemDataRole.UserRole, item.path)

        self.list_widget.addItem(list_item)

    def _update_list_display(self):
        """リスト表示を更新（順序番号を振り直し）"""
        for i in range(self.list_widget.count()):
            list_item = self.list_widget.item(i)
            path = list_item.data(Qt.ItemDataRole.UserRole)

            # 対応するSelectionItemを検索
            selection_item = next((item for item in self._items if item.path == path), None)
            if selection_item:
                display_text = f"{i + 1}. {selection_item.name} [{selection_item.label}]"
                list_item.setText(display_text)

    def _update_count(self):
        """カウント表示を更新"""
        self.count_label.setText(f"選択数: {len(self._items)}")

    def _on_rows_moved(self, parent, start, end, destination, row):
        """ドラッグ&ドロップで行が移動した時の処理"""
        # リストウィジェットの順序に合わせて_itemsを再構築
        new_items = []
        for i in range(self.list_widget.count()):
            list_item = self.list_widget.item(i)
            path = list_item.data(Qt.ItemDataRole.UserRole)

            # 対応するSelectionItemを検索
            selection_item = next((item for item in self._items if item.path == path), None)
            if selection_item:
                new_items.append(selection_item)

        self._items = new_items

        # 表示を更新
        self._update_list_display()

        # シグナル発火
        self.items_changed.emit()

        logger.debug("アイテムの順序が変更されました")

    def _move_up(self):
        """選択アイテムを上に移動"""
        current_row = self.list_widget.currentRow()
        if current_row > 0:
            # リストアイテムを移動
            item = self.list_widget.takeItem(current_row)
            self.list_widget.insertItem(current_row - 1, item)
            self.list_widget.setCurrentRow(current_row - 1)

            # _itemsも移動
            self._items[current_row], self._items[current_row - 1] = \
                self._items[current_row - 1], self._items[current_row]

            # 表示更新
            self._update_list_display()

            # シグナル発火
            self.items_changed.emit()

    def _move_down(self):
        """選択アイテムを下に移動"""
        current_row = self.list_widget.currentRow()
        if current_row < self.list_widget.count() - 1 and current_row >= 0:
            # リストアイテムを移動
            item = self.list_widget.takeItem(current_row)
            self.list_widget.insertItem(current_row + 1, item)
            self.list_widget.setCurrentRow(current_row + 1)

            # _itemsも移動
            self._items[current_row], self._items[current_row + 1] = \
                self._items[current_row + 1], self._items[current_row]

            # 表示更新
            self._update_list_display()

            # シグナル発火
            self.items_changed.emit()

    def _remove_selected(self):
        """選択されているアイテムを削除"""
        current_row = self.list_widget.currentRow()
        if current_row >= 0:
            list_item = self.list_widget.item(current_row)
            path = list_item.data(Qt.ItemDataRole.UserRole)
            self.remove_item(path)

    def _apply_label_to_all(self):
        """選択されたアイテム（または全体）にラベルを一括適用"""
        label = self.label_input.text().strip()
        if not label:
            label = "全景"

        # バスケット内で選択されているアイテムを取得
        selected_items = self.list_widget.selectedItems()

        if selected_items:
            # 選択されたアイテムのみにラベルを適用
            count = 0
            for list_item in selected_items:
                path = list_item.data(Qt.ItemDataRole.UserRole)
                # 対応するSelectionItemを検索
                for item in self._items:
                    if item.path == path:
                        item.label = label
                        count += 1
                        break

            logger.info(f"{count}個の選択アイテムにラベル '{label}' を適用")
        else:
            # 選択がない場合は全体に適用
            for item in self._items:
                item.label = label

            logger.info(f"すべてのアイテムにラベル '{label}' を適用")

        # 表示を更新
        self._update_list_display()

        # シグナル発火
        self.items_changed.emit()

    def set_label_for_item(self, index: int, label: str):
        """
        特定のアイテムのラベルを設定

        Args:
            index: アイテムのインデックス
            label: 新しいラベル
        """
        if 0 <= index < len(self._items):
            self._items[index].label = label
            self._update_list_display()
            self.items_changed.emit()

    def set_selected_paths(self, paths: set[str]):
        """
        選択中の画像パスを設定

        Args:
            paths: 選択中の画像パスのセット
        """
        self._selected_paths = paths.copy()

    def apply_label_to_selected(self, label: str) -> int:
        """
        選択中の画像にラベルを適用

        Args:
            label: 適用するラベル

        Returns:
            ラベルを適用したアイテム数
        """
        count = 0
        for item in self._items:
            if item.path in self._selected_paths:
                item.label = label
                count += 1

        if count > 0:
            self._update_list_display()
            self.items_changed.emit()
            self.label_applied.emit(label)
            logger.info(f"{count}個のアイテムにラベル '{label}' を適用")

        return count

    def get_selected_item_count(self) -> int:
        """
        選択中のアイテム数を取得

        Returns:
            選択中のアイテム数
        """
        return len([item for item in self._items if item.path in self._selected_paths])

    def apply_label_to_bucket_selected(self, label: str) -> int:
        """
        バスケット内で選択されているアイテムにラベルを適用
        バスケット内で何も選択されていない場合は、ThumbnailGridで選択された画像に適用

        Args:
            label: 適用するラベル

        Returns:
            ラベルを適用したアイテム数
        """
        # バスケット内で選択されているアイテムを取得
        selected_list_items = self.list_widget.selectedItems()

        count = 0

        if selected_list_items:
            # バスケット内で選択されたアイテムにラベルを適用
            for list_item in selected_list_items:
                path = list_item.data(Qt.ItemDataRole.UserRole)
                for item in self._items:
                    if item.path == path:
                        item.label = label
                        count += 1
                        break

            logger.info(f"バスケット内の{count}個の選択アイテムにラベル '{label}' を適用")
        else:
            # ThumbnailGridで選択された画像にラベルを適用（従来の動作）
            for item in self._items:
                if item.path in self._selected_paths:
                    item.label = label
                    count += 1

            if count > 0:
                logger.info(f"{count}個のアイテムにラベル '{label}' を適用")

        if count > 0:
            self._update_list_display()
            self.items_changed.emit()
            self.label_applied.emit(label)

        return count

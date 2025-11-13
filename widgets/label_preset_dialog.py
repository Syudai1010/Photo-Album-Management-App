"""
ラベルプリセット設定ダイアログ
ユーザーが番号とラベル名を追加・編集できる
"""
import logging
from typing import Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QMessageBox, QHeaderView, QLineEdit
)

logger = logging.getLogger(__name__)


class LabelPresetDialog(QDialog):
    """ラベルプリセット設定ダイアログ"""

    def __init__(self, presets: Dict[int, str], parent=None):
        """
        Args:
            presets: 番号 -> ラベル名の辞書
            parent: 親ウィジェット
        """
        super().__init__(parent)
        self.presets = presets.copy()
        self._setup_ui()
        self._load_presets()

    def _setup_ui(self):
        """UIセットアップ"""
        self.setWindowTitle("ラベルプリセット設定")
        self.setMinimumSize(500, 400)

        layout = QVBoxLayout(self)

        # 説明
        info_label = QLabel(
            "テンキーの番号に対応するラベルを設定してください。\n"
            "番号1-9を使用できます。"
        )
        info_label.setStyleSheet("color: #666; margin-bottom: 10px;")
        layout.addWidget(info_label)

        # テーブル
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["番号", "ラベル名"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 80)
        layout.addWidget(self.table)

        # 追加エリア
        add_layout = QHBoxLayout()

        add_label = QLabel("新規追加:")
        add_layout.addWidget(add_label)

        self.number_input = QLineEdit()
        self.number_input.setPlaceholderText("番号 (1-9)")
        self.number_input.setMaximumWidth(100)
        add_layout.addWidget(self.number_input)

        self.label_input = QLineEdit()
        self.label_input.setPlaceholderText("ラベル名")
        add_layout.addWidget(self.label_input)

        self.add_btn = QPushButton("追加")
        self.add_btn.clicked.connect(self._add_preset)
        add_layout.addWidget(self.add_btn)

        layout.addLayout(add_layout)

        # ボタンエリア
        button_layout = QHBoxLayout()

        self.delete_btn = QPushButton("選択を削除")
        self.delete_btn.clicked.connect(self._delete_selected)
        button_layout.addWidget(self.delete_btn)

        button_layout.addStretch()

        self.ok_btn = QPushButton("OK")
        self.ok_btn.setDefault(True)
        self.ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.ok_btn)

        self.cancel_btn = QPushButton("キャンセル")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def _load_presets(self):
        """プリセットをテーブルに読み込み"""
        self.table.setRowCount(0)

        # 番号順にソート
        sorted_presets = sorted(self.presets.items())

        for number, label in sorted_presets:
            self._add_row(number, label)

    def _add_row(self, number: int, label: str):
        """テーブルに行を追加"""
        row = self.table.rowCount()
        self.table.insertRow(row)

        # 番号（読み取り専用）
        number_item = QTableWidgetItem(str(number))
        number_item.setFlags(number_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        number_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 0, number_item)

        # ラベル名（編集可能）
        label_item = QTableWidgetItem(label)
        self.table.setItem(row, 1, label_item)

    def _add_preset(self):
        """新しいプリセットを追加"""
        # 番号を取得
        number_text = self.number_input.text().strip()
        if not number_text:
            QMessageBox.warning(self, "入力エラー", "番号を入力してください。")
            return

        try:
            number = int(number_text)
            if number < 1 or number > 9:
                QMessageBox.warning(self, "入力エラー", "番号は1-9の範囲で入力してください。")
                return
        except ValueError:
            QMessageBox.warning(self, "入力エラー", "番号は数字で入力してください。")
            return

        # ラベル名を取得
        label = self.label_input.text().strip()
        if not label:
            QMessageBox.warning(self, "入力エラー", "ラベル名を入力してください。")
            return

        # 重複チェック
        if number in self.presets:
            reply = QMessageBox.question(
                self,
                "確認",
                f"番号 {number} は既に存在します。上書きしますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # プリセットに追加
        self.presets[number] = label

        # テーブルを再読み込み
        self._load_presets()

        # 入力欄をクリア
        self.number_input.clear()
        self.label_input.clear()

        logger.info(f"ラベルプリセット追加: {number} -> {label}")

    def _delete_selected(self):
        """選択されたプリセットを削除"""
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "選択エラー", "削除する項目を選択してください。")
            return

        # 番号を取得
        number_item = self.table.item(current_row, 0)
        number = int(number_item.text())

        # 確認
        label = self.presets[number]
        reply = QMessageBox.question(
            self,
            "確認",
            f"番号 {number} ({label}) を削除しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # プリセットから削除
            del self.presets[number]

            # テーブルを再読み込み
            self._load_presets()

            logger.info(f"ラベルプリセット削除: {number} -> {label}")

    def get_presets(self) -> Dict[int, str]:
        """
        現在のプリセットを取得（テーブルの編集内容を反映）

        Returns:
            番号 -> ラベル名の辞書
        """
        # テーブルの内容を取得
        result = {}
        for row in range(self.table.rowCount()):
            number_item = self.table.item(row, 0)
            label_item = self.table.item(row, 1)

            if number_item and label_item:
                number = int(number_item.text())
                label = label_item.text().strip()

                if label:  # 空でない場合のみ追加
                    result[number] = label

        return result

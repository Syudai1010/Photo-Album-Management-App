"""
フォトブック管理アプリケーション - メイン
サムネイル選択→順序付け→一括リネーム機能を提供
"""
# --- main.py の先頭付近に追加（QApplicationを作る前！） ---
import os
def _ensure_qt_plugin_path():
    try:
        import PySide6
        base = os.path.dirname(PySide6.__file__)
        plugins = os.path.join(base, "plugins")
        platforms = os.path.join(plugins, "platforms")
        # 既にユーザが設定していれば尊重し、無ければ補う
        os.environ.setdefault("QT_PLUGIN_PATH", plugins)
        os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", platforms)
        # 予防的にPATHへもplatformsを追加（DLL検索のため）
        if platforms not in os.environ.get("PATH",""):
            os.environ["PATH"] = platforms + os.pathsep + os.environ.get("PATH","")
    except Exception as e:
        print("Qt plugins path setup failed:", e)

_ensure_qt_plugin_path()
# --------------------------------------------------------------

import sys
import logging
import json
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QTextEdit, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QSplitter, QComboBox, QMessageBox, QDialog
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QKeyEvent, QShortcut, QKeySequence

from widgets.thumbnail_grid import ThumbnailGrid
from widgets.selection_bucket import SelectionBucket
from widgets.label_preset_dialog import LabelPresetDialog
from services.renamer import Renamer, RenameRow

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class LogHandler(logging.Handler):
    """GUIにログを表示するハンドラ"""

    def __init__(self, text_widget: QTextEdit):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        """ログレコードを処理"""
        try:
            msg = self.format(record)

            # レベルに応じた色分け
            if record.levelno >= logging.ERROR:
                color = "#D32F2F"  # 赤
                prefix = "[ERROR]"
            elif record.levelno >= logging.WARNING:
                color = "#F57C00"  # オレンジ
                prefix = "[WARN]"
            else:
                color = "#333333"  # 黒
                prefix = "[INFO]"

            # HTMLで色付けして追加
            html_msg = f'<span style="color: {color};"><b>{prefix}</b> {msg}</span>'
            self.text_widget.append(html_msg)

            # 自動スクロール
            self.text_widget.verticalScrollBar().setValue(
                self.text_widget.verticalScrollBar().maximum()
            )

        except Exception:
            self.handleError(record)


class PhotoRenamerApp(QMainWindow):
    """メインアプリケーションウィンドウ"""

    def __init__(self):
        super().__init__()
        self.renamer = Renamer()
        self.current_folder: Path | None = None
        self.preview_rows: list[RenameRow] = []

        # ラベルプリセット（番号 -> ラベル名）
        self.label_presets = {
            1: "全景",
            2: "接写",
            3: "内部",
            4: "測定",
            5: "詳細",
            6: "外観"
        }

        self._setup_ui()
        self._setup_logging()
        self._connect_signals()
        self._setup_shortcuts()

        logger.info("アプリケーション起動")
        logger.info(f"ラベルプリセット: {self.label_presets}")

    def _setup_ui(self):
        """UIセットアップ"""
        self.setWindowTitle("フォトブック管理 - 画像リネームツール")
        self.setGeometry(100, 100, 1400, 800)

        # 中央ウィジェット
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)

        # 左ペイン：サムネイルグリッド
        left_pane = self._create_left_pane()
        main_layout.addWidget(left_pane, stretch=2)

        # 中央ペイン：選択バスケット
        center_pane = self._create_center_pane()
        main_layout.addWidget(center_pane, stretch=1)

        # 右ペイン：操作とプレビュー
        right_pane = self._create_right_pane()
        main_layout.addWidget(right_pane, stretch=2)

    def _create_left_pane(self) -> QWidget:
        """左ペイン（サムネイルグリッド）を作成"""
        pane = QWidget()
        layout = QVBoxLayout(pane)

        # タイトルとフォルダ選択
        title_layout = QHBoxLayout()
        title_label = QLabel("画像フォルダ")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_layout.addWidget(title_label)

        self.open_folder_btn = QPushButton("フォルダを開く")
        self.open_folder_btn.setStyleSheet("background-color: #2196F3; color: white; padding: 5px 15px;")
        title_layout.addWidget(self.open_folder_btn)

        layout.addLayout(title_layout)

        # フォルダパス表示
        self.folder_path_label = QLabel("フォルダが選択されていません")
        self.folder_path_label.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(self.folder_path_label)

        # 選択をバスケットに追加ボタン
        add_to_basket_layout = QHBoxLayout()
        self.add_to_basket_btn = QPushButton("選択をバスケットに追加")
        self.add_to_basket_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px 15px; font-weight: bold;")
        self.add_to_basket_btn.clicked.connect(self._add_selected_to_bucket)
        add_to_basket_layout.addWidget(self.add_to_basket_btn)
        add_to_basket_layout.addStretch()
        layout.addLayout(add_to_basket_layout)

        # 操作説明
        help_label = QLabel("Ctrl+クリックで複数選択 → ボタンで一括追加 → テンキーでラベル適用")
        help_label.setStyleSheet("color: #666; font-size: 9px; font-style: italic;")
        layout.addWidget(help_label)

        # サムネイルグリッド
        self.thumbnail_grid = ThumbnailGrid()
        layout.addWidget(self.thumbnail_grid)

        return pane

    def _create_center_pane(self) -> QWidget:
        """中央ペイン（選択バスケット）を作成"""
        pane = QWidget()
        layout = QVBoxLayout(pane)

        # 選択バスケット
        self.selection_bucket = SelectionBucket()
        layout.addWidget(self.selection_bucket)

        return pane

    def _create_right_pane(self) -> QWidget:
        """右ペイン（操作とプレビュー）を作成"""
        pane = QWidget()
        layout = QVBoxLayout(pane)

        # タイトル
        title_label = QLabel("リネーム設定")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)

        # 命名テンプレート
        template_layout = QHBoxLayout()
        template_layout.addWidget(QLabel("テンプレート:"))

        self.template_input = QLineEdit("V-{seq:1}_{label}")
        template_layout.addWidget(self.template_input)

        layout.addLayout(template_layout)

        # ヘルプテキスト
        help_text = QLabel("変数: {group}=グループ番号, {label}=ラベル, {seq:003}=連番（ゼロ埋め3桁）")
        help_text.setStyleSheet("color: #666; font-size: 9px;")
        layout.addWidget(help_text)

        # ラベルプリセット
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("ラベルプリセット:"))

        self.label_preset_combo = QComboBox()
        self._update_preset_combo()
        preset_layout.addWidget(self.label_preset_combo)

        self.apply_preset_btn = QPushButton("選択項目に適用")
        self.apply_preset_btn.clicked.connect(self._apply_label_preset)
        preset_layout.addWidget(self.apply_preset_btn)

        # プリセット設定ボタン
        self.preset_settings_btn = QPushButton("設定...")
        self.preset_settings_btn.clicked.connect(self._open_preset_settings)
        preset_layout.addWidget(self.preset_settings_btn)

        layout.addLayout(preset_layout)

        # キーボードショートカット表示
        shortcut_label = QLabel("ショートカット: 数字キー 1-9 でラベル適用（NumLock on ならテンキーも可）、Deleteで選択クリア")
        shortcut_label.setStyleSheet("color: #666; font-size: 9px; font-style: italic;")
        layout.addWidget(shortcut_label)

        # アクションボタン
        button_layout = QHBoxLayout()

        self.preview_btn = QPushButton("プレビュー")
        self.preview_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px 20px;")
        button_layout.addWidget(self.preview_btn)

        self.execute_btn = QPushButton("実行")
        self.execute_btn.setStyleSheet("background-color: #FF5722; color: white; padding: 8px 20px;")
        self.execute_btn.setEnabled(False)
        button_layout.addWidget(self.execute_btn)

        self.undo_btn = QPushButton("Undo")
        self.undo_btn.setStyleSheet("background-color: #9E9E9E; color: white; padding: 8px 20px;")
        button_layout.addWidget(self.undo_btn)

        layout.addLayout(button_layout)

        # JSON出力ボタン
        json_button_layout = QHBoxLayout()
        self.export_json_btn = QPushButton("JSON出力")
        self.export_json_btn.setStyleSheet("background-color: #673AB7; color: white; padding: 8px 20px;")
        self.export_json_btn.clicked.connect(self._export_to_json)
        json_button_layout.addWidget(self.export_json_btn)
        json_button_layout.addStretch()

        layout.addLayout(json_button_layout)

        # プレビューテーブル
        preview_label = QLabel("プレビュー")
        preview_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(preview_label)

        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(2)
        self.preview_table.setHorizontalHeaderLabels(["旧ファイル名", "新ファイル名"])
        self.preview_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.preview_table)

        # ログビュー
        log_label = QLabel("ログ")
        log_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(log_label)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        layout.addWidget(self.log_text)

        return pane

    def _setup_logging(self):
        """ロギングをGUIに接続"""
        log_handler = LogHandler(self.log_text)
        log_handler.setFormatter(logging.Formatter('%(message)s'))
        logging.getLogger().addHandler(log_handler)

    def _connect_signals(self):
        """シグナルとスロットを接続"""
        # フォルダ選択
        self.open_folder_btn.clicked.connect(self._open_folder)

        # サムネイルクリック
        self.thumbnail_grid.image_clicked.connect(self._on_image_clicked)

        # バスケットクリア時に一覧の選択もクリア
        self.selection_bucket.cleared.connect(self._on_bucket_cleared)

        # プレビュー・実行・Undo
        self.preview_btn.clicked.connect(self._preview_rename)
        self.execute_btn.clicked.connect(self._execute_rename)
        self.undo_btn.clicked.connect(self._undo_rename)

    def _setup_shortcuts(self):
        """キーボードショートカットをセットアップ（フォーカスに依存しない）"""
        # 数字キー 1-9 でラベル適用（NumLock on ならテンキーも自動で含まれる）
        for number in range(1, 10):
            if number in self.label_presets:
                shortcut = QShortcut(QKeySequence(str(number)), self)
                shortcut.activated.connect(lambda n=number: self._apply_label_by_number(n))

    def keyPressEvent(self, event: QKeyEvent):
        """キーボードイベント処理"""
        key = event.key()

        # Deleteキーで選択クリア
        if key == Qt.Key.Key_Delete:
            self._clear_thumbnail_selection()
            event.accept()
            return

        super().keyPressEvent(event)

    def _open_folder(self):
        """フォルダを開く"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "画像フォルダを選択",
            str(Path.home())
        )

        if folder:
            self.current_folder = Path(folder)
            self.folder_path_label.setText(str(self.current_folder))

            # サムネイルグリッドに読み込み
            self.thumbnail_grid.load_folder(folder)

            logger.info(f"フォルダを開きました: {folder}")

    def _on_image_clicked(self, file_path: str):
        """画像クリック時の処理"""
        # 一覧の選択状態変更のみ（ThumbnailGrid側で処理済み）
        # バスケットへの追加は「選択をバスケットに追加」ボタンで行う
        pass

    def _add_selected_to_bucket(self):
        """一覧で選択中の画像をすべてバスケットに追加"""
        # 選択中の画像パスを取得
        selected_paths = self.thumbnail_grid.get_selected_paths()

        if not selected_paths:
            logger.warning("画像が選択されていません")
            return

        # 選択された画像をすべてバスケットに追加
        added_count = 0
        for path in selected_paths:
            # まだバスケットに無い場合のみ追加
            if not self.selection_bucket.has_item(path):
                self.selection_bucket.add_item(path, label="全景", group=1)
                added_count += 1

        # 選択状態を維持（バスケットに通知）
        self.selection_bucket.set_selected_paths(set(selected_paths))

        if added_count > 0:
            logger.info(f"{added_count}個の画像をバスケットに追加しました（選択状態を維持）")
        else:
            logger.info("選択された画像はすべてバスケットに存在しています")

    def _apply_label_preset(self):
        """ラベルプリセットをバスケット内の選択項目に適用"""
        # データ部分を取得（"1. 全景" ではなく "全景" のみ）
        label = self.label_preset_combo.currentData()

        if not label:
            logger.warning("ラベルが選択されていません")
            return

        # 選択中の画像パスを取得（ThumbnailGridから）
        selected_paths = self.thumbnail_grid.get_selected_paths()
        self.selection_bucket.set_selected_paths(selected_paths)

        # バスケット内で選択されているアイテムにラベルを適用
        count = self.selection_bucket.apply_label_to_bucket_selected(label)

        if count > 0:
            logger.info(f"ラベル '{label}' を {count} 個のアイテムに適用しました")
            # ラベル適用後、一覧の選択をクリア（次の選択を明確にする）
            self._clear_thumbnail_selection()
        else:
            logger.warning("バスケット内で選択されたアイテムがありません")

    def _preview_rename(self):
        """リネームのプレビューを生成"""
        items = self.selection_bucket.get_items_dict()

        if not items:
            logger.warning("選択されたアイテムがありません")
            return

        # テンプレートを取得
        template = self.template_input.text().strip()
        if not template:
            template = "V-{group}_{label}_{seq:003}"

        # プレビュー生成
        self.preview_rows = self.renamer.preview(items, template)

        # テーブルに表示
        self.preview_table.setRowCount(len(self.preview_rows))

        for idx, row in enumerate(self.preview_rows):
            # 旧ファイル名
            old_item = QTableWidgetItem(row.old_name)
            self.preview_table.setItem(idx, 0, old_item)

            # 新ファイル名
            new_item = QTableWidgetItem(row.new_name)

            # 重複チェック（警告色）
            if row.old_name != row.new_name and row.new_path.exists():
                new_item.setBackground(QColor("#FFEB3B"))  # 黄色
            elif row.old_name != row.new_name:
                new_item.setBackground(QColor("#C8E6C9"))  # 緑

            self.preview_table.setItem(idx, 1, new_item)

        # 実行ボタンを有効化
        self.execute_btn.setEnabled(True)

        logger.info(f"{len(self.preview_rows)}件のプレビューを生成しました")

    def _execute_rename(self):
        """リネームを実行"""
        if not self.preview_rows:
            logger.warning("プレビューを先に生成してください")
            return

        # 確認ダイアログ
        reply = QMessageBox.question(
            self,
            "確認",
            f"{len(self.preview_rows)}個のファイルをリネームしますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # リネーム実行
        logger.info("リネームを実行中...")
        result = self.renamer.execute(self.preview_rows)

        # 結果を表示
        logger.info(f"リネーム完了: 成功 {result['success']}件, 失敗 {result['failed']}件")

        if result['errors']:
            for error in result['errors']:
                logger.error(error)

        # 成功した場合
        if result['success'] > 0:
            QMessageBox.information(
                self,
                "完了",
                f"{result['success']}個のファイルをリネームしました。"
            )

            # バスケットとプレビューをクリア
            self.selection_bucket.clear()
            self.preview_table.setRowCount(0)
            self.preview_rows.clear()
            self.execute_btn.setEnabled(False)

            # サムネイルグリッドを再読み込み
            if self.current_folder:
                self.thumbnail_grid.load_folder(str(self.current_folder))

    def _undo_rename(self):
        """直前のリネームを元に戻す"""
        # 確認ダイアログ
        reply = QMessageBox.question(
            self,
            "確認",
            "直前のリネームを元に戻しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Undo実行
        logger.info("Undoを実行中...")
        result = self.renamer.undo()

        # 結果を表示
        logger.info(f"Undo完了: 成功 {result['success']}件, 失敗 {result['failed']}件")

        if result['errors']:
            for error in result['errors']:
                logger.error(error)

        # 成功した場合
        if result['success'] > 0:
            QMessageBox.information(
                self,
                "完了",
                f"{result['success']}個のファイルを元に戻しました。"
            )

            # サムネイルグリッドを再読み込み
            if self.current_folder:
                self.thumbnail_grid.load_folder(str(self.current_folder))

    def _apply_label_by_number(self, number: int):
        """
        番号に対応するラベルを選択中の画像に適用
        バスケット内で選択されている場合はそれを優先、なければThumbnailGridの選択を使用

        Args:
            number: プリセット番号 (1-9)
        """
        if number not in self.label_presets:
            logger.warning(f"番号 {number} に対応するラベルが設定されていません")
            return

        label = self.label_presets[number]

        # 選択中の画像パスを取得（ThumbnailGridから）
        selected_paths = self.thumbnail_grid.get_selected_paths()
        self.selection_bucket.set_selected_paths(selected_paths)

        # ラベルを適用（バスケット内の選択を優先）
        count = self.selection_bucket.apply_label_to_bucket_selected(label)

        if count > 0:
            logger.info(f"番号 {number} ({label}) を {count} 個の画像に適用")
            # ラベル適用後、一覧の選択をクリア（次の選択を明確にする）
            self._clear_thumbnail_selection()
        else:
            logger.warning("選択中の画像がバスケットにありません")

    def _on_bucket_cleared(self):
        """バスケットがクリアされた時の処理"""
        # サムネイルグリッドの選択もクリア
        self._clear_thumbnail_selection()

        # プレビューテーブルもクリア
        self.preview_table.setRowCount(0)
        self.preview_rows.clear()
        self.execute_btn.setEnabled(False)
        logger.info("プレビューをクリアしました")

    def _clear_thumbnail_selection(self):
        """サムネイルグリッドの選択をクリア"""
        self.thumbnail_grid.selected_paths.clear()

        # すべてのサムネイルの選択状態をリセット
        for path, item in self.thumbnail_grid.thumbnail_items.items():
            item.set_selected(False)

        logger.info("画像の選択をクリアしました")

    def _update_preset_combo(self):
        """プリセットコンボボックスを更新"""
        self.label_preset_combo.clear()

        # 番号順にソート
        sorted_presets = sorted(self.label_presets.items())

        for number, label in sorted_presets:
            self.label_preset_combo.addItem(f"{number}. {label}", label)

    def _open_preset_settings(self):
        """ラベルプリセット設定ダイアログを開く"""
        dialog = LabelPresetDialog(self.label_presets, self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            # プリセットを更新
            self.label_presets = dialog.get_presets()

            # コンボボックスを更新
            self._update_preset_combo()

            logger.info(f"ラベルプリセットを更新しました: {self.label_presets}")

    def _export_to_json(self):
        """バスケットの内容をJSON形式でエクスポート"""
        items = self.selection_bucket.get_items_dict()

        if not items:
            logger.warning("バスケットにアイテムがありません")
            QMessageBox.warning(
                self,
                "警告",
                "バスケットにアイテムがありません。\n画像を選択してからJSON出力してください。"
            )
            return

        # 保存先を選択
        default_filename = f"photobook_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "JSON出力",
            str(Path.home() / default_filename),
            "JSON Files (*.json);;All Files (*)"
        )

        if not file_path:
            return

        # JSONデータを構築
        export_data = {
            "export_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_count": len(items),
            "items": []
        }

        for idx, item in enumerate(items, start=1):
            export_data["items"].append({
                "order": idx,
                "file_name": Path(item['path']).name,
                "file_path": item['path'],
                "label": item['label'],
                "group": item['group']
            })

        # JSONファイルに書き込み
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)

            logger.info(f"JSON出力完了: {file_path} ({len(items)}件)")
            QMessageBox.information(
                self,
                "完了",
                f"{len(items)}件のアイテムをJSON出力しました。\n{file_path}"
            )

        except Exception as e:
            logger.error(f"JSON出力エラー: {e}")
            QMessageBox.critical(
                self,
                "エラー",
                f"JSON出力に失敗しました。\n{str(e)}"
            )


def main():
    """メイン関数"""
    app = QApplication(sys.argv)

    # アプリケーションスタイル
    app.setStyle('Fusion')

    # メインウィンドウ
    window = PhotoRenamerApp()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()

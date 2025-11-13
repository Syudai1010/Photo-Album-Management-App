"""
ファイルリネームサービス
一括リネーム・プレビュー・Undo機能を提供
"""
import csv
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from utils.pathsafe import get_unique_path, is_valid_filename, sanitize_filename

logger = logging.getLogger(__name__)


@dataclass
class RenameRow:
    """リネーム情報を保持するデータクラス"""
    old_path: Path
    new_path: Path
    old_name: str
    new_name: str
    success: bool = False
    error_message: str = ""

    def __post_init__(self):
        """初期化後の処理"""
        if isinstance(self.old_path, str):
            self.old_path = Path(self.old_path)
        if isinstance(self.new_path, str):
            self.new_path = Path(self.new_path)


class Renamer:
    """ファイルリネーム機能を提供するクラス"""

    def __init__(self, rename_map_path: Optional[str | Path] = None):
        """
        Args:
            rename_map_path: リネームマップCSVの保存先パス
        """
        self.rename_map_path = Path(rename_map_path) if rename_map_path else Path("rename_map.csv")

    def preview(self, items: List[dict], template: str = "V-{group}_{label}_{seq:003}") -> List[RenameRow]:
        """
        リネームのプレビューを生成

        Args:
            items: リネーム対象のアイテムリスト
                   各アイテムは {'path': str, 'label': str, 'group': int} の形式
            template: 命名テンプレート

        Returns:
            RenameRowのリスト
        """
        rows = []

        for idx, item in enumerate(items):
            try:
                old_path = Path(item['path'])
                if not old_path.exists():
                    logger.warning(f"ファイルが存在しません: {old_path}")
                    continue

                # テンプレートから新しいファイル名を生成
                new_name = self._apply_template(
                    template=template,
                    group=item.get('group', 1),
                    label=item.get('label', '全景'),
                    seq=idx + 1,
                    extension=old_path.suffix
                )

                # ファイル名の検証とサニタイズ
                if not is_valid_filename(new_name):
                    new_name = sanitize_filename(new_name)

                new_path = old_path.parent / new_name

                # 重複チェック
                if new_path.exists() and new_path != old_path:
                    logger.warning(f"ファイルが既に存在します: {new_path}")
                    # 重複回避のため番号を付与
                    new_path = get_unique_path(new_path)
                    new_name = new_path.name

                row = RenameRow(
                    old_path=old_path,
                    new_path=new_path,
                    old_name=old_path.name,
                    new_name=new_name
                )
                rows.append(row)

            except Exception as e:
                logger.error(f"プレビュー生成エラー ({item.get('path', 'unknown')}): {e}")

        return rows

    def execute(self, rows: List[RenameRow]) -> dict:
        """
        リネームを実行

        Args:
            rows: リネーム情報のリスト

        Returns:
            実行結果の辞書 {'success': int, 'failed': int, 'errors': List[str]}
        """
        result = {
            'success': 0,
            'failed': 0,
            'errors': []
        }

        executed_rows = []
        start_time = datetime.now()

        for row in rows:
            try:
                # ファイルの存在確認
                if not row.old_path.exists():
                    error_msg = f"ファイルが存在しません: {row.old_path}"
                    row.error_message = error_msg
                    result['errors'].append(error_msg)
                    result['failed'] += 1
                    continue

                # 同じパスの場合はスキップ
                if row.old_path == row.new_path:
                    logger.info(f"同じファイル名のためスキップ: {row.old_path}")
                    row.success = True
                    result['success'] += 1
                    executed_rows.append(row)
                    continue

                # リネーム実行
                row.old_path.rename(row.new_path)
                row.success = True
                result['success'] += 1
                executed_rows.append(row)

                logger.info(f"リネーム成功: {row.old_name} -> {row.new_name}")

            except PermissionError as e:
                error_msg = f"権限エラー: {row.old_path} - ファイルが使用中か、書き込み権限がありません"
                row.error_message = error_msg
                result['errors'].append(error_msg)
                result['failed'] += 1
                logger.error(error_msg)

            except OSError as e:
                error_msg = f"OSエラー: {row.old_path} - {str(e)}"
                row.error_message = error_msg
                result['errors'].append(error_msg)
                result['failed'] += 1
                logger.error(error_msg)

            except Exception as e:
                error_msg = f"予期しないエラー: {row.old_path} - {str(e)}"
                row.error_message = error_msg
                result['errors'].append(error_msg)
                result['failed'] += 1
                logger.error(error_msg)

        # リネームマップをCSVに保存
        if executed_rows:
            self._save_rename_map(executed_rows, start_time)

        return result

    def undo(self) -> dict:
        """
        直近のリネームを元に戻す

        Returns:
            実行結果の辞書 {'success': int, 'failed': int, 'errors': List[str]}
        """
        result = {
            'success': 0,
            'failed': 0,
            'errors': []
        }

        # リネームマップを読み込み
        rows = self._load_latest_rename_map()

        if not rows:
            result['errors'].append("Undo可能なリネーム履歴がありません")
            return result

        # 逆順でリネーム（新 -> 旧）
        for row in reversed(rows):
            try:
                # 現在のパス（リネーム後）が存在するか確認
                if not row.new_path.exists():
                    error_msg = f"ファイルが存在しません: {row.new_path}"
                    result['errors'].append(error_msg)
                    result['failed'] += 1
                    continue

                # 元のパスに戻す
                row.new_path.rename(row.old_path)
                result['success'] += 1

                logger.info(f"Undo成功: {row.new_name} -> {row.old_name}")

            except Exception as e:
                error_msg = f"Undoエラー: {row.new_path} - {str(e)}"
                result['errors'].append(error_msg)
                result['failed'] += 1
                logger.error(error_msg)

        return result

    def _apply_template(self, template: str, group: int, label: str, seq: int, extension: str) -> str:
        """
        テンプレートを適用して新しいファイル名を生成

        Args:
            template: 命名テンプレート
            group: グループ番号
            label: ラベル
            seq: 連番
            extension: 拡張子

        Returns:
            生成されたファイル名
        """
        # {group} を置換
        result = template.replace('{group}', str(group))

        # {label} を置換
        result = result.replace('{label}', label)

        # {seq:NNN} を置換（ゼロ埋め対応）
        seq_pattern = r'\{seq:(\d+)\}'
        match = re.search(seq_pattern, result)
        if match:
            width = int(match.group(1))
            seq_str = str(seq).zfill(width)
            result = re.sub(seq_pattern, seq_str, result)
        else:
            # {seq} のみの場合
            result = result.replace('{seq}', str(seq))

        # 拡張子を追加（テンプレートに含まれていない場合）
        if not result.endswith(extension):
            result += extension

        return result

    def _save_rename_map(self, rows: List[RenameRow], timestamp: datetime) -> None:
        """
        リネームマップをCSVに保存

        Args:
            rows: リネーム情報のリスト
            timestamp: 実行日時
        """
        try:
            file_exists = self.rename_map_path.exists()

            with open(self.rename_map_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # ヘッダー（ファイルが新規の場合のみ）
                if not file_exists:
                    writer.writerow(['timestamp', 'old_name', 'new_name', 'old_full_path', 'new_full_path', 'success'])

                # データ行
                for row in rows:
                    writer.writerow([
                        timestamp.isoformat(),
                        row.old_name,
                        row.new_name,
                        str(row.old_path),
                        str(row.new_path),
                        row.success
                    ])

            logger.info(f"リネームマップを保存しました: {self.rename_map_path}")

        except Exception as e:
            logger.error(f"リネームマップの保存に失敗: {e}")

    def _load_latest_rename_map(self) -> List[RenameRow]:
        """
        最新のリネームマップを読み込み

        Returns:
            RenameRowのリスト
        """
        if not self.rename_map_path.exists():
            logger.warning("リネームマップファイルが存在しません")
            return []

        try:
            with open(self.rename_map_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows_data = list(reader)

            if not rows_data:
                return []

            # 最新のタイムスタンプを取得
            latest_timestamp = rows_data[-1]['timestamp']

            # 最新のタイムスタンプの行のみを抽出
            latest_rows = []
            for row_data in reversed(rows_data):
                if row_data['timestamp'] != latest_timestamp:
                    break

                row = RenameRow(
                    old_path=Path(row_data['old_full_path']),
                    new_path=Path(row_data['new_full_path']),
                    old_name=row_data['old_name'],
                    new_name=row_data['new_name'],
                    success=row_data['success'].lower() == 'true'
                )
                latest_rows.append(row)

            return list(reversed(latest_rows))

        except Exception as e:
            logger.error(f"リネームマップの読み込みに失敗: {e}")
            return []

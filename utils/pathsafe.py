"""
パス操作のユーティリティモジュール
Windows環境での日本語ファイル名・長いパスに対応
"""
import os
import re
from pathlib import Path
from typing import Optional


def normalize_path(path: str | Path) -> Path:
    """
    パスを正規化してPathオブジェクトとして返す

    Args:
        path: 正規化するパス

    Returns:
        正規化されたPathオブジェクト
    """
    return Path(path).resolve()


def is_valid_filename(filename: str) -> bool:
    """
    ファイル名が有効かどうかをチェック

    Args:
        filename: チェックするファイル名

    Returns:
        有効な場合True
    """
    # Windows/Mac/Linuxで使用できない文字をチェック
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    if re.search(invalid_chars, filename):
        return False

    # Windowsの予約語をチェック
    reserved_names = ['CON', 'PRN', 'AUX', 'NUL',
                     'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
                     'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9']

    name_without_ext = os.path.splitext(filename)[0].upper()
    if name_without_ext in reserved_names:
        return False

    return True


def sanitize_filename(filename: str, replacement: str = '_') -> str:
    """
    ファイル名を安全な形式にサニタイズ

    Args:
        filename: サニタイズするファイル名
        replacement: 無効な文字の置き換え文字

    Returns:
        サニタイズされたファイル名
    """
    # 無効な文字を置き換え
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    sanitized = re.sub(invalid_chars, replacement, filename)

    # 先頭・末尾のスペースとドットを削除
    sanitized = sanitized.strip(' .')

    # 空になった場合のデフォルト
    if not sanitized:
        sanitized = 'unnamed'

    return sanitized


def get_unique_path(base_path: Path) -> Path:
    """
    重複しないパスを取得（存在する場合は(1), (2)などを付与）

    Args:
        base_path: ベースとなるパス

    Returns:
        重複しないパス
    """
    if not base_path.exists():
        return base_path

    stem = base_path.stem
    suffix = base_path.suffix
    parent = base_path.parent

    counter = 1
    while True:
        new_name = f"{stem} ({counter}){suffix}"
        new_path = parent / new_name
        if not new_path.exists():
            return new_path
        counter += 1


def get_safe_path(path: str | Path, max_length: int = 255) -> Optional[Path]:
    """
    安全なパスを取得（長さ制限を考慮）

    Args:
        path: 元のパス
        max_length: ファイル名の最大長

    Returns:
        安全なパス（変換できない場合None）
    """
    try:
        p = normalize_path(path)

        # ファイル名の長さチェック
        if len(p.name) > max_length:
            # 拡張子を保持しつつ短縮
            stem = p.stem[:max_length - len(p.suffix) - 3] + '...'
            new_name = stem + p.suffix
            p = p.parent / new_name

        return p
    except Exception:
        return None


def ensure_directory(directory: str | Path) -> bool:
    """
    ディレクトリが存在することを保証（なければ作成）

    Args:
        directory: ディレクトリパス

    Returns:
        成功した場合True
    """
    try:
        Path(directory).mkdir(parents=True, exist_ok=True)
        return True
    except Exception:
        return False


def get_file_extension(path: str | Path) -> str:
    """
    ファイルの拡張子を小文字で取得

    Args:
        path: ファイルパス

    Returns:
        小文字の拡張子（ドット付き、例：'.jpg'）
    """
    return Path(path).suffix.lower()


def is_image_file(path: str | Path) -> bool:
    """
    画像ファイルかどうかを判定

    Args:
        path: ファイルパス

    Returns:
        画像ファイルの場合True
    """
    image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.tif', '.heic', '.heif'}
    return get_file_extension(path) in image_extensions

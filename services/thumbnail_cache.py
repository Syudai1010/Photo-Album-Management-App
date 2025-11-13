"""
サムネイルキャッシュサービス
大量の画像を効率的に表示するためのキャッシュ機構
"""
import logging
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtCore import QSize

logger = logging.getLogger(__name__)

# HEIC対応（複数のライブラリを試行）
HEIC_AVAILABLE = False
HEIC_METHOD = None

# pillow-heifを優先（インストールが簡単）
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC_AVAILABLE = True
    HEIC_METHOD = "pillow_heif"
    logger.info("pillow-heifが利用可能です。HEIC画像に対応します。")
except ImportError:
    pass

# pyheifを次に試行
if not HEIC_AVAILABLE:
    try:
        import pyheif
        HEIC_AVAILABLE = True
        HEIC_METHOD = "pyheif"
        logger.info("pyheifが利用可能です。HEIC画像に対応します。")
    except ImportError:
        logger.info("HEIC対応ライブラリがインストールされていません。JPG/PNG等のみ対応します。")


class ThumbnailCache:
    """サムネイルをキャッシュするクラス"""

    def __init__(self, max_cache_size: int = 500):
        """
        Args:
            max_cache_size: キャッシュする最大サムネイル数
        """
        self._cache: dict[str, QPixmap] = {}
        self._max_cache_size = max_cache_size
        self._access_order: list[str] = []  # LRU用のアクセス順序

    def get(self, file_path: str | Path, size: Tuple[int, int] = (200, 200)) -> Optional[QPixmap]:
        """
        サムネイルを取得（キャッシュにあればそれを返し、なければ生成）

        Args:
            file_path: 画像ファイルのパス
            size: サムネイルのサイズ (width, height)

        Returns:
            サムネイルのQPixmap（取得できない場合None）
        """
        file_path = str(Path(file_path))
        cache_key = f"{file_path}_{size[0]}x{size[1]}"

        # キャッシュにあれば返す
        if cache_key in self._cache:
            self._update_access(cache_key)
            return self._cache[cache_key]

        # サムネイルを生成
        pixmap = self._generate_thumbnail(file_path, size)
        if pixmap:
            self._add_to_cache(cache_key, pixmap)

        return pixmap

    def _generate_thumbnail(self, file_path: str, size: Tuple[int, int]) -> Optional[QPixmap]:
        """
        サムネイルを生成

        Args:
            file_path: 画像ファイルのパス
            size: サムネイルのサイズ

        Returns:
            生成されたQPixmap（失敗時None）
        """
        try:
            path = Path(file_path)
            if not path.exists():
                logger.warning(f"ファイルが存在しません: {file_path}")
                return None

            # HEIC対応
            if path.suffix.lower() in ['.heic', '.heif']:
                # pillow-heifの場合は標準的な方法で読み込める
                if HEIC_METHOD == "pillow_heif":
                    return self._generate_standard_thumbnail(file_path, size)
                # pyheifの場合は専用メソッドを使用
                elif HEIC_METHOD == "pyheif":
                    return self._generate_heic_thumbnail(file_path, size)
                else:
                    logger.warning(f"HEICファイルはサポートされていません: {file_path}")
                    return None

            # 通常の画像ファイル
            return self._generate_standard_thumbnail(file_path, size)

        except Exception as e:
            logger.error(f"サムネイル生成エラー ({file_path}): {e}")
            return None

    def _generate_standard_thumbnail(self, file_path: str, size: Tuple[int, int]) -> Optional[QPixmap]:
        """
        標準的な画像形式のサムネイルを生成

        Args:
            file_path: 画像ファイルのパス
            size: サムネイルのサイズ

        Returns:
            生成されたQPixmap
        """
        try:
            with Image.open(file_path) as img:
                # RGBA変換（透明度対応）
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')

                # サムネイル生成（アスペクト比維持）
                img.thumbnail(size, Image.Resampling.LANCZOS)

                # PIL Image -> QPixmap
                return self._pil_to_qpixmap(img)

        except Exception as e:
            logger.error(f"標準画像のサムネイル生成エラー ({file_path}): {e}")
            return None

    def _generate_heic_thumbnail(self, file_path: str, size: Tuple[int, int]) -> Optional[QPixmap]:
        """
        HEIC形式のサムネイルを生成

        Args:
            file_path: HEICファイルのパス
            size: サムネイルのサイズ

        Returns:
            生成されたQPixmap（HEIC非対応の場合None）
        """
        if not HEIC_AVAILABLE:
            logger.warning(f"HEICファイルはサポートされていません: {file_path}")
            return None

        try:
            # HEICファイルを読み込み
            heif_file = pyheif.read(file_path)

            # PIL Imageに変換
            img = Image.frombytes(
                heif_file.mode,
                heif_file.size,
                heif_file.data,
                "raw",
                heif_file.mode,
                heif_file.stride,
            )

            # RGB変換
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # サムネイル生成
            img.thumbnail(size, Image.Resampling.LANCZOS)

            # PIL Image -> QPixmap
            return self._pil_to_qpixmap(img)

        except Exception as e:
            logger.error(f"HEICサムネイル生成エラー ({file_path}): {e}")
            return None

    def _pil_to_qpixmap(self, pil_image: Image.Image) -> QPixmap:
        """
        PIL ImageをQPixmapに変換

        Args:
            pil_image: PIL Imageオブジェクト

        Returns:
            QPixmap
        """
        # PIL Image -> bytes
        img_bytes = pil_image.tobytes('raw', 'RGB')

        # QImage作成
        qimage = QImage(
            img_bytes,
            pil_image.width,
            pil_image.height,
            pil_image.width * 3,  # bytes per line
            QImage.Format.Format_RGB888
        )

        # QPixmapに変換
        return QPixmap.fromImage(qimage)

    def _add_to_cache(self, key: str, pixmap: QPixmap) -> None:
        """
        キャッシュに追加（LRU方式）

        Args:
            key: キャッシュキー
            pixmap: QPixmap
        """
        # キャッシュサイズ制限
        if len(self._cache) >= self._max_cache_size:
            # 最も古いアクセスのアイテムを削除
            if self._access_order:
                oldest_key = self._access_order.pop(0)
                del self._cache[oldest_key]

        self._cache[key] = pixmap
        self._access_order.append(key)

    def _update_access(self, key: str) -> None:
        """
        アクセス順序を更新（LRU用）

        Args:
            key: キャッシュキー
        """
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

    def clear(self) -> None:
        """キャッシュをクリア"""
        self._cache.clear()
        self._access_order.clear()

    def get_cache_size(self) -> int:
        """
        現在のキャッシュサイズを取得

        Returns:
            キャッシュされているアイテム数
        """
        return len(self._cache)

    def is_heic_supported(self) -> bool:
        """
        HEIC形式がサポートされているかチェック

        Returns:
            サポートされている場合True
        """
        return HEIC_AVAILABLE

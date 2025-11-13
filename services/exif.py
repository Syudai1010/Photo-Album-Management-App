"""
EXIF情報読み取りサービス
撮影日時などのメタデータを取得
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import exifread
    EXIFREAD_AVAILABLE = True
except ImportError:
    EXIFREAD_AVAILABLE = False

try:
    import piexif
    PIEXIF_AVAILABLE = True
except ImportError:
    PIEXIF_AVAILABLE = False

from PIL import Image

logger = logging.getLogger(__name__)


class ExifReader:
    """EXIF情報を読み取るクラス"""

    @staticmethod
    def read_datetime(file_path: str | Path) -> Optional[datetime]:
        """
        画像ファイルから撮影日時を読み取る

        Args:
            file_path: 画像ファイルのパス

        Returns:
            撮影日時（取得できない場合はNone）
        """
        file_path = Path(file_path)

        if not file_path.exists():
            logger.warning(f"ファイルが存在しません: {file_path}")
            return None

        # まずPILのEXIFを試す
        dt = ExifReader._read_datetime_pil(file_path)
        if dt:
            return dt

        # 次にpiexifを試す
        if PIEXIF_AVAILABLE:
            dt = ExifReader._read_datetime_piexif(file_path)
            if dt:
                return dt

        # 最後にexifreadを試す
        if EXIFREAD_AVAILABLE:
            dt = ExifReader._read_datetime_exifread(file_path)
            if dt:
                return dt

        # すべて失敗した場合はファイルの更新日時を返す
        logger.debug(f"EXIF情報が取得できないため、ファイル更新日時を使用: {file_path}")
        return ExifReader._get_file_mtime(file_path)

    @staticmethod
    def _read_datetime_pil(file_path: Path) -> Optional[datetime]:
        """PILを使用して撮影日時を読み取る"""
        try:
            with Image.open(file_path) as img:
                exif_data = img._getexif()
                if exif_data:
                    # 0x9003: DateTimeOriginal (撮影日時)
                    # 0x0132: DateTime (更新日時)
                    for tag in [0x9003, 0x0132]:
                        if tag in exif_data:
                            dt_str = exif_data[tag]
                            return ExifReader._parse_exif_datetime(dt_str)
        except Exception as e:
            logger.debug(f"PIL EXIF読み取りエラー ({file_path}): {e}")
        return None

    @staticmethod
    def _read_datetime_piexif(file_path: Path) -> Optional[datetime]:
        """piexifを使用して撮影日時を読み取る"""
        try:
            exif_dict = piexif.load(str(file_path))

            # Exif IFDから撮影日時を取得
            if piexif.ExifIFD.DateTimeOriginal in exif_dict.get("Exif", {}):
                dt_bytes = exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal]
                dt_str = dt_bytes.decode('utf-8') if isinstance(dt_bytes, bytes) else dt_bytes
                return ExifReader._parse_exif_datetime(dt_str)

            # 0th IFDから更新日時を取得
            if piexif.ImageIFD.DateTime in exif_dict.get("0th", {}):
                dt_bytes = exif_dict["0th"][piexif.ImageIFD.DateTime]
                dt_str = dt_bytes.decode('utf-8') if isinstance(dt_bytes, bytes) else dt_bytes
                return ExifReader._parse_exif_datetime(dt_str)

        except Exception as e:
            logger.debug(f"piexif EXIF読み取りエラー ({file_path}): {e}")
        return None

    @staticmethod
    def _read_datetime_exifread(file_path: Path) -> Optional[datetime]:
        """exifreadを使用して撮影日時を読み取る"""
        try:
            with open(file_path, 'rb') as f:
                tags = exifread.process_file(f, details=False)

                # EXIF DateTimeOriginal (撮影日時)
                if 'EXIF DateTimeOriginal' in tags:
                    dt_str = str(tags['EXIF DateTimeOriginal'])
                    return ExifReader._parse_exif_datetime(dt_str)

                # Image DateTime (更新日時)
                if 'Image DateTime' in tags:
                    dt_str = str(tags['Image DateTime'])
                    return ExifReader._parse_exif_datetime(dt_str)

        except Exception as e:
            logger.debug(f"exifread EXIF読み取りエラー ({file_path}): {e}")
        return None

    @staticmethod
    def _parse_exif_datetime(dt_str: str) -> Optional[datetime]:
        """
        EXIF日時文字列をdatetimeオブジェクトに変換

        Args:
            dt_str: EXIF日時文字列（例：'2023:12:25 14:30:45'）

        Returns:
            datetimeオブジェクト（変換できない場合None）
        """
        try:
            # EXIF標準フォーマット: "YYYY:MM:DD HH:MM:SS"
            return datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
        except ValueError:
            try:
                # ハイフン区切りの場合も試す
                return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                logger.debug(f"EXIF日時のパースに失敗: {dt_str}")
                return None

    @staticmethod
    def _get_file_mtime(file_path: Path) -> Optional[datetime]:
        """
        ファイルの更新日時を取得

        Args:
            file_path: ファイルパス

        Returns:
            更新日時
        """
        try:
            mtime = file_path.stat().st_mtime
            return datetime.fromtimestamp(mtime)
        except Exception as e:
            logger.error(f"ファイル更新日時の取得に失敗: {file_path}, {e}")
            return None

    @staticmethod
    def get_image_info(file_path: str | Path) -> dict:
        """
        画像の基本情報を取得

        Args:
            file_path: 画像ファイルのパス

        Returns:
            画像情報の辞書
        """
        file_path = Path(file_path)
        info = {
            'path': str(file_path),
            'name': file_path.name,
            'size': 0,
            'width': 0,
            'height': 0,
            'datetime': None,
        }

        try:
            # ファイルサイズ
            info['size'] = file_path.stat().st_size

            # 画像サイズと撮影日時
            with Image.open(file_path) as img:
                info['width'], info['height'] = img.size

            # 撮影日時
            info['datetime'] = ExifReader.read_datetime(file_path)

        except Exception as e:
            logger.warning(f"画像情報の取得に失敗: {file_path}, {e}")

        return info

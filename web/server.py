"""
フォトブック管理アプリケーション - Web版サーバー
Flask ベースのローカルサーバー
"""
import sys
import os
import webbrowser
from pathlib import Path
from datetime import datetime
import json
import base64
from threading import Timer

# 親ディレクトリをパスに追加（既存のservicesモジュールを使用するため）
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

# 既存のサービスを再利用
from services.thumbnail_cache import ThumbnailCache
from services.exif import ExifReader
from services.renamer import Renamer, RenameRow
from utils.pathsafe import is_image_file

app = Flask(__name__, static_folder='static', template_folder='static')
CORS(app)

# グローバル変数
thumbnail_cache = ThumbnailCache(max_cache_size=500)
renamer = Renamer()
current_session = {
    'folder': None,
    'images': [],
    'basket': []
}

# ラベルプリセット
LABEL_PRESETS = {
    1: "全景",
    2: "接写",
    3: "内部",
    4: "測定",
    5: "詳細",
    6: "外観"
}


@app.route('/')
def index():
    """メインページ"""
    return send_from_directory('static', 'index.html')


@app.route('/api/folder/browse', methods=['POST'])
def browse_folder():
    """フォルダを参照"""
    data = request.json
    folder_path = data.get('path')

    if not folder_path or not os.path.exists(folder_path):
        return jsonify({'error': 'Invalid folder path'}), 400

    folder = Path(folder_path)
    if not folder.is_dir():
        return jsonify({'error': 'Not a directory'}), 400

    # 画像ファイルを収集
    images = []
    for file_path in folder.iterdir():
        if file_path.is_file() and is_image_file(file_path):
            # EXIF情報取得
            dt = ExifReader.read_datetime(file_path)

            images.append({
                'path': str(file_path),
                'name': file_path.name,
                'datetime': dt.isoformat() if dt else None,
                'size': file_path.stat().st_size
            })

    # セッションに保存
    current_session['folder'] = folder_path
    current_session['images'] = images

    return jsonify({
        'folder': folder_path,
        'images': images,
        'count': len(images)
    })


@app.route('/api/folder/list-drives', methods=['GET'])
def list_drives():
    """利用可能なドライブ/ディレクトリを取得（クロスプラットフォーム対応）"""
    drives = []

    if os.name == 'nt':  # Windows
        import string
        from ctypes import windll

        bitmask = windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drive_path = f"{letter}:\\"
                if os.path.exists(drive_path):
                    drives.append({
                        'path': drive_path,
                        'name': f"{letter}:\\ ドライブ",
                        'type': 'drive'
                    })
            bitmask >>= 1
    else:  # Unix系（Mac, Linux）
        # ホームディレクトリ
        home = str(Path.home())
        drives.append({
            'path': home,
            'name': 'ホーム',
            'type': 'directory'
        })

        # ルートディレクトリ
        drives.append({
            'path': '/',
            'name': 'ルート (/)',
            'type': 'directory'
        })

        # よく使うディレクトリ
        common_dirs = [
            (Path.home() / 'Documents', 'ドキュメント'),
            (Path.home() / 'Pictures', '画像'),
            (Path.home() / 'Desktop', 'デスクトップ'),
            (Path.home() / 'Downloads', 'ダウンロード'),
        ]

        for path, name in common_dirs:
            if path.exists():
                drives.append({
                    'path': str(path),
                    'name': name,
                    'type': 'directory'
                })

    return jsonify({'drives': drives})


@app.route('/api/folder/list-subdirs', methods=['POST'])
def list_subdirectories():
    """指定されたパスのサブディレクトリを取得"""
    data = request.json
    parent_path = data.get('path')

    if not parent_path or not os.path.exists(parent_path):
        return jsonify({'error': 'Invalid path'}), 400

    parent = Path(parent_path)
    if not parent.is_dir():
        return jsonify({'error': 'Not a directory'}), 400

    subdirs = []
    try:
        for item in parent.iterdir():
            if item.is_dir():
                try:
                    subdirs.append({
                        'path': str(item),
                        'name': item.name
                    })
                except PermissionError:
                    pass  # アクセス権限がない場合はスキップ
    except PermissionError:
        return jsonify({'error': 'Permission denied'}), 403

    # 名前順にソート
    subdirs.sort(key=lambda x: x['name'].lower())

    return jsonify({'subdirs': subdirs})


@app.route('/api/images/sort', methods=['POST'])
def sort_images():
    """画像をソート"""
    data = request.json
    mode = data.get('mode', 'name')  # name, exif_asc, exif_desc

    images = current_session.get('images', [])

    if mode == 'name':
        images.sort(key=lambda x: x['name'])
    elif mode in ['exif_asc', 'exif_desc']:
        # datetime でソート（None の場合は最小値として扱う）
        images.sort(
            key=lambda x: x['datetime'] if x['datetime'] else '',
            reverse=(mode == 'exif_desc')
        )

    current_session['images'] = images

    return jsonify({'images': images})


@app.route('/api/thumbnail/<path:file_path>')
def get_thumbnail(file_path):
    """サムネイルを取得"""
    # パスをデコード
    file_path = '/' + file_path  # Unixパスの場合

    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404

    # サムネイル生成
    pixmap = thumbnail_cache.get(file_path, size=(200, 200))

    if not pixmap:
        return jsonify({'error': 'Failed to generate thumbnail'}), 500

    # QPixmap を base64 エンコードされた画像データに変換
    from PySide6.QtCore import QBuffer, QIODevice
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, 'PNG')
    image_data = base64.b64encode(buffer.data()).decode('utf-8')

    return jsonify({
        'data': f"data:image/png;base64,{image_data}"
    })


@app.route('/api/basket/add', methods=['POST'])
def add_to_basket():
    """バスケットにアイテムを追加"""
    data = request.json
    items = data.get('items', [])

    basket = current_session.get('basket', [])

    for item in items:
        # 重複チェック
        if not any(b['path'] == item['path'] for b in basket):
            basket.append({
                'path': item['path'],
                'name': item['name'],
                'label': item.get('label', '全景'),
                'group': item.get('group', 1)
            })

    current_session['basket'] = basket

    return jsonify({
        'basket': basket,
        'count': len(basket)
    })


@app.route('/api/basket/remove', methods=['POST'])
def remove_from_basket():
    """バスケットからアイテムを削除"""
    data = request.json
    path = data.get('path')

    basket = current_session.get('basket', [])
    basket = [item for item in basket if item['path'] != path]

    current_session['basket'] = basket

    return jsonify({
        'basket': basket,
        'count': len(basket)
    })


@app.route('/api/basket/clear', methods=['POST'])
def clear_basket():
    """バスケットをクリア"""
    current_session['basket'] = []

    return jsonify({'success': True})


@app.route('/api/basket/reorder', methods=['POST'])
def reorder_basket():
    """バスケットの順序を変更"""
    data = request.json
    new_order = data.get('basket', [])

    current_session['basket'] = new_order

    return jsonify({'success': True})


@app.route('/api/basket/update-label', methods=['POST'])
def update_label():
    """バスケット内のアイテムのラベルを更新"""
    data = request.json
    paths = data.get('paths', [])
    label = data.get('label')

    basket = current_session.get('basket', [])

    count = 0
    for item in basket:
        if item['path'] in paths:
            item['label'] = label
            count += 1

    current_session['basket'] = basket

    return jsonify({
        'success': True,
        'count': count,
        'basket': basket
    })


@app.route('/api/labels/presets', methods=['GET'])
def get_label_presets():
    """ラベルプリセットを取得"""
    return jsonify({'presets': LABEL_PRESETS})


@app.route('/api/rename/preview', methods=['POST'])
def preview_rename():
    """リネームのプレビューを生成"""
    data = request.json
    template = data.get('template', 'V-{group}_{label}_{seq:003}')

    basket = current_session.get('basket', [])

    if not basket:
        return jsonify({'error': 'Basket is empty'}), 400

    # プレビュー生成
    preview_rows = renamer.preview(basket, template)

    # RenameRow を辞書に変換
    preview_data = []
    for row in preview_rows:
        preview_data.append({
            'old_name': row.old_name,
            'new_name': row.new_name,
            'old_path': str(row.old_path),
            'new_path': str(row.new_path),
            'exists': row.new_path.exists() and row.old_path != row.new_path
        })

    return jsonify({
        'preview': preview_data,
        'count': len(preview_data)
    })


@app.route('/api/rename/execute', methods=['POST'])
def execute_rename():
    """リネームを実行"""
    data = request.json
    template = data.get('template', 'V-{group}_{label}_{seq:003}')

    basket = current_session.get('basket', [])

    if not basket:
        return jsonify({'error': 'Basket is empty'}), 400

    # プレビュー生成
    preview_rows = renamer.preview(basket, template)

    # リネーム実行
    result = renamer.execute(preview_rows)

    # バスケットをクリア（成功した場合）
    if result['success'] > 0:
        current_session['basket'] = []

        # 画像リストも更新（フォルダを再読み込み）
        if current_session['folder']:
            folder = Path(current_session['folder'])
            images = []
            for file_path in folder.iterdir():
                if file_path.is_file() and is_image_file(file_path):
                    dt = ExifReader.read_datetime(file_path)
                    images.append({
                        'path': str(file_path),
                        'name': file_path.name,
                        'datetime': dt.isoformat() if dt else None,
                        'size': file_path.stat().st_size
                    })
            current_session['images'] = images

    return jsonify(result)


@app.route('/api/rename/undo', methods=['POST'])
def undo_rename():
    """リネームを元に戻す"""
    result = renamer.undo()

    # 成功した場合、画像リストを更新
    if result['success'] > 0 and current_session['folder']:
        folder = Path(current_session['folder'])
        images = []
        for file_path in folder.iterdir():
            if file_path.is_file() and is_image_file(file_path):
                dt = ExifReader.read_datetime(file_path)
                images.append({
                    'path': str(file_path),
                    'name': file_path.name,
                    'datetime': dt.isoformat() if dt else None,
                    'size': file_path.stat().st_size
                })
        current_session['images'] = images

    return jsonify(result)


@app.route('/api/export/json', methods=['POST'])
def export_json():
    """バスケットの内容をJSON形式でエクスポート"""
    basket = current_session.get('basket', [])

    if not basket:
        return jsonify({'error': 'Basket is empty'}), 400

    # JSONデータを構築
    export_data = {
        'export_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_count': len(basket),
        'items': []
    }

    for idx, item in enumerate(basket, start=1):
        export_data['items'].append({
            'order': idx,
            'file_name': Path(item['path']).name,
            'file_path': item['path'],
            'label': item['label'],
            'group': item['group']
        })

    return jsonify(export_data)


def open_browser():
    """ブラウザを自動的に開く"""
    webbrowser.open('http://127.0.0.1:5000')


if __name__ == '__main__':
    print("=" * 60)
    print("フォトブック管理アプリケーション - Web版")
    print("=" * 60)
    print()
    print("サーバーを起動しています...")
    print("ブラウザで以下のURLを開いてください:")
    print()
    print("    http://127.0.0.1:5000")
    print()
    print("終了するには Ctrl+C を押してください")
    print("=" * 60)

    # 1秒後にブラウザを自動的に開く
    Timer(1.5, open_browser).start()

    # Flaskサーバー起動
    app.run(debug=True, host='127.0.0.1', port=5000, use_reloader=False)

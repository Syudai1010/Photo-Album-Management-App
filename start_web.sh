#!/bin/bash
# フォトブック管理アプリケーション - Web版起動スクリプト (Mac/Linux)

echo "=============================="
echo "フォトブック管理 - Web版"
echo "=============================="
echo ""

# 依存関係のチェックとインストール
echo "依存関係を確認中..."
if ! python3 -c "import flask" &> /dev/null; then
    echo "Flask がインストールされていません。インストール中..."
    pip3 install -r web/requirements-web.txt
    if [ $? -ne 0 ]; then
        echo ""
        echo "エラー: 依存関係のインストールに失敗しました。"
        echo "手動で以下のコマンドを実行してください:"
        echo "  pip3 install -r web/requirements-web.txt"
        exit 1
    fi
fi

echo ""
echo "サーバーを起動しています..."
echo "ブラウザが自動的に開きます。"
echo ""
echo "終了するには Ctrl+C を押してください。"
echo "=============================="
echo ""

# サーバー起動
cd web
python3 server.py

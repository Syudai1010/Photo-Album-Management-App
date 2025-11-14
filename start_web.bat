@echo off
REM フォトブック管理アプリケーション - Web版起動スクリプト (Windows)

echo ==============================
echo フォトブック管理 - Web版
echo ==============================
echo.

REM 依存関係のチェックとインストール
echo 依存関係を確認中...
pip show Flask >nul 2>&1
if errorlevel 1 (
    echo Flask がインストールされていません。インストール中...
    pip install -r web\requirements-web.txt
    if errorlevel 1 (
        echo.
        echo エラー: 依存関係のインストールに失敗しました。
        echo 手動で以下のコマンドを実行してください:
        echo   pip install -r web\requirements-web.txt
        pause
        exit /b 1
    )
)

echo.
echo サーバーを起動しています...
echo ブラウザが自動的に開きます。
echo.
echo 終了するには Ctrl+C を押してください。
echo ==============================
echo.

REM サーバー起動
cd web
python server.py

pause

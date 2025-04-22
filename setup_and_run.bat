@echo off
setlocal enabledelayedexpansion

echo.
echo HotPepper Beauty 画像投稿ツール セットアップと実行
echo.

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"
echo 作業ディレクトリ: %CD%
echo.

echo [Step 1/4] Python 確認中...
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo ==================== エラー ====================
    echo Pythonが見つかりません。
    echo Pythonをインストールし、「Add Python to PATH」にチェックを入れてください。
    echo ==============================================
    echo.
    pause
    exit /b 1
) else (
    echo Python OK.
    for /f "tokens=*" %%i in ('python --version') do set PYTHON_VERSION=%%i
    echo バージョン: !PYTHON_VERSION!
)
echo.

echo [Step 2/4] ライブラリ準備中...
if not exist "requirements.txt" (
    echo ==================== エラー ====================
    echo 必須ファイル requirements.txt が見つかりません。
    echo このバッチファイルと同じ場所に requirements.txt があるか確認してください。
    echo ==============================================
    echo.
    pause
    exit /b 1
)

set INSTALLED=1
pip freeze | findstr /R /C:"^PyQt6==" > nul || set INSTALLED=0
pip freeze | findstr /R /C:"^playwright==" > nul || set INSTALLED=0
pip freeze | findstr /R /C:"^requests==" > nul || set INSTALLED=0
pip freeze | findstr /R /C:"^beautifulsoup4==" > nul || set INSTALLED=0

if !INSTALLED! equ 0 (
    echo ライブラリをインストールします 所要時間 数分...
    pip install -r requirements.txt
    if !errorlevel! neq 0 (
        echo ==================== エラー ====================
        echo ライブラリのインストールに失敗しました。
        echo インターネット接続やセキュリティソフトを確認してください。
        echo ==============================================
        echo.
        pause
        exit /b 1
    ) else (
        echo ライブラリ インストール完了。
    )
) else (
    echo ライブラリ OK.
)
echo.

echo [Step 3/4] ブラウザ準備中 初回は時間がかかります...
playwright install
if !errorlevel! neq 0 (
    echo ==================== 警告 ====================
    echo Playwrightブラウザの準備に問題発生 エラーコード: !errorlevel!
    echo 画像投稿時に問題が出る可能性があります。
    echo ==============================================
    echo.
    pause
) else (
    echo ブラウザ OK.
)
echo.

echo [Step 4/4] アプリケーション起動中...
echo.
python -m src.app
if !errorlevel! neq 0 (
    echo ==================== エラー ====================
    echo アプリケーションの起動に失敗 エラーコード: !errorlevel!
    echo ==============================================
    echo.
    pause
    exit /b 1
)

echo.
echo ==================================================
echo アプリケーションを終了しました。
echo ==================================================
endlocal
pause
exit /b 0
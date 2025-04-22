@echo off
setlocal enabledelayedexpansion

echo.
echo HotPepper Beauty �摜���e�c�[�� �Z�b�g�A�b�v�Ǝ��s
echo.

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"
echo ��ƃf�B���N�g��: %CD%
echo.

echo [Step 1/4] Python �m�F��...
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo ==================== �G���[ ====================
    echo Python��������܂���B
    echo Python���C���X�g�[�����A�uAdd Python to PATH�v�Ƀ`�F�b�N�����Ă��������B
    echo ==============================================
    echo.
    pause
    exit /b 1
) else (
    echo Python OK.
    for /f "tokens=*" %%i in ('python --version') do set PYTHON_VERSION=%%i
    echo �o�[�W����: !PYTHON_VERSION!
)
echo.

echo [Step 2/4] ���C�u����������...
if not exist "requirements.txt" (
    echo ==================== �G���[ ====================
    echo �K�{�t�@�C�� requirements.txt ��������܂���B
    echo ���̃o�b�`�t�@�C���Ɠ����ꏊ�� requirements.txt �����邩�m�F���Ă��������B
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
    echo ���C�u�������C���X�g�[�����܂� ���v���� ����...
    pip install -r requirements.txt
    if !errorlevel! neq 0 (
        echo ==================== �G���[ ====================
        echo ���C�u�����̃C���X�g�[���Ɏ��s���܂����B
        echo �C���^�[�l�b�g�ڑ���Z�L�����e�B�\�t�g���m�F���Ă��������B
        echo ==============================================
        echo.
        pause
        exit /b 1
    ) else (
        echo ���C�u���� �C���X�g�[�������B
    )
) else (
    echo ���C�u���� OK.
)
echo.

echo [Step 3/4] �u���E�U������ ����͎��Ԃ�������܂�...
playwright install
if !errorlevel! neq 0 (
    echo ==================== �x�� ====================
    echo Playwright�u���E�U�̏����ɖ�蔭�� �G���[�R�[�h: !errorlevel!
    echo �摜���e���ɖ�肪�o��\��������܂��B
    echo ==============================================
    echo.
    pause
) else (
    echo �u���E�U OK.
)
echo.

echo [Step 4/4] �A�v���P�[�V�����N����...
echo.
python -m src.app
if !errorlevel! neq 0 (
    echo ==================== �G���[ ====================
    echo �A�v���P�[�V�����̋N���Ɏ��s �G���[�R�[�h: !errorlevel!
    echo ==============================================
    echo.
    pause
    exit /b 1
)

echo.
echo ==================================================
echo �A�v���P�[�V�������I�����܂����B
echo ==================================================
endlocal
pause
exit /b 0
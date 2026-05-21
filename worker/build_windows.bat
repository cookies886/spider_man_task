@echo off
REM SpiderMan Windows Worker 打包脚本
REM 在 Windows 机器上跑这个 .bat 即可产出 dist_release\windows_worker_1.0.zip

setlocal
chcp 65001 >NUL
cd /d "%~dp0"

echo [INFO] 检查 Python ...
python --version >NUL 2>&1
if errorlevel 1 (
    echo [ERR] 没装 Python。请先安装 Python 3.10+
    pause
    exit /b 1
)

if not exist .venv (
    echo [INFO] 创建虚拟环境 .venv
    python -m venv .venv
)

echo [INFO] 激活并安装依赖
call .venv\Scripts\activate
pip install --quiet --upgrade pip
pip install --quiet -e .
pip install --quiet pyinstaller

echo [INFO] 开始打包
python build_windows.py
if errorlevel 1 (
    echo [ERR] 打包失败
    pause
    exit /b 1
)

echo.
echo ==========================================
echo  打包完成 ^| 产物：dist_release\windows_worker_1.0.zip
echo ==========================================
pause

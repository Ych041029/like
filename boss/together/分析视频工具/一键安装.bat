@echo off
REM 游戏任务分析工具 - 环境一键安装
REM 双击此文件即可自动安装Python依赖库
REM 前提: 已安装Python 3.8-3.10 (python --version 能看到版本)
chcp 65001 >nul
title 游戏任务分析工具 - 环境安装

echo ============================================================
echo   游戏任务分析工具 - 环境一键安装
echo ============================================================
echo.

REM 检查Python
echo [1/4] 检查Python...
python --version >nul 2>nul
if errorlevel 1 (
    echo.
    echo [错误] 没检测到Python!
    echo 请先安装 Python 3.8-3.10 (从 https://www.python.org 下载)
    echo 安装时务必勾选 "Add Python to PATH"
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo   Python版本: %PYVER%  [OK]
echo.

REM 检查pip
echo [2/4] 检查pip...
python -m pip --version >nul 2>nul
if errorlevel 1 (
    echo   [警告] pip未就绪,正在安装...
    python -m ensurepip --upgrade
)
echo   pip就绪  [OK]
echo.

REM 升级pip(避免老版本pip装paddle报错)
echo [3/4] 升级pip...
python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
echo.

REM 安装依赖
echo [4/4] 安装依赖库(numpy/paddlepaddle/paddleocr/Pillow)...
echo   (使用清华镜像源加速,首次约需5-15分钟)
echo.
python -m pip install -r "%~dp0requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo.
    echo [错误] 依赖安装失败!
    echo 可能原因: 网络问题 / Python版本不兼容
    echo 请检查报错信息,或手动执行: pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   安装完成!
echo ============================================================
echo.

REM 验证安装
echo 正在验证安装...
python -c "import numpy; print('  numpy:        OK', numpy.__version__)"
python -c "import paddle; print('  paddlepaddle: OK')" 2>nul || echo   paddlepaddle: [未验证]
python -c "import paddleocr; print('  paddleocr:    OK')" 2>nul || echo   paddleocr:    [未验证,首次运行会自动下载模型]
python -c "from PIL import Image; print('  Pillow:       OK')"

echo.
echo 如果以上都显示OK,环境就装好了。
echo.
echo 接下来还需要:
echo   1. 安装 ffmpeg (用于视频抽帧) - 见 环境安装说明.md
echo   2. 首次运行工具会自动下载PaddleOCR中文模型(约100MB)
echo.
pause

@echo off
REM 整合工具(任务1+任务2) - 环境一键安装
REM 双击此文件即可自动安装Python依赖库
REM 前提1: 已安装Python 3.8-3.10 (python --version 能看到版本)
REM 前提2: 已安装ffmpeg并加入PATH (ffmpeg -version 能看到版本)
chcp 936 >nul
title 整合工具 - 环境一键安装

echo ============================================================
echo   整合工具(游戏概述+任务时间线) - 环境一键安装
echo ============================================================
echo.

REM 检查Python
echo [1/5] 检查Python...
python --version >nul 2>nul
if errorlevel 1 (
    echo.
    echo [错误] 没检测到Python!
    echo 请先安装 Python 3.8-3.10 ^(从 https://www.python.org 下载^)
    echo 安装时务必勾选 "Add Python to PATH"
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo   Python版本: %PYVER%  [OK]
echo.

REM 检查ffmpeg
echo [2/5] 检查ffmpeg...
ffmpeg -version >nul 2>nul
if errorlevel 1 (
    echo.
    echo [错误] 没检测到ffmpeg!
    echo 请先安装 ffmpeg 并加入PATH:
    echo   1. 从 https://www.gyan.dev/ffmpeg/builds/ 下载 ffmpeg-release-essentials.zip
    echo   2. 解压到如 C:\ffmpeg
    echo   3. 把 C:\ffmpeg\bin 加入系统环境变量 Path
    echo   4. 重启命令行后重试
    echo.
    pause
    exit /b 1
)
echo   ffmpeg已就绪  [OK]
echo.

REM 检查pip
echo [3/5] 检查pip...
python -m pip --version >nul 2>nul
if errorlevel 1 (
    echo   [警告] pip未就绪,正在安装...
    python -m ensurepip --upgrade
)
echo   pip就绪  [OK]
echo.

REM 升级pip(避免老版本pip装paddle报错)
echo [4/5] 升级pip...
python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
echo.

REM 安装依赖
echo [5/5] 安装依赖库(numpy/paddlepaddle/paddleocr/Pillow/matplotlib)...
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
echo   安装完成! 正在验证...
echo ============================================================
echo.
python -c "import numpy; print('  numpy:        OK', numpy.__version__)"
python -c "import paddle; print('  paddlepaddle: OK')" 2>nul || echo   paddlepaddle: [未验证]
python -c "import paddleocr; print('  paddleocr:    OK')" 2>nul || echo   paddleocr:    [未验证,首次运行会自动下载模型]
python -c "from PIL import Image; print('  Pillow:       OK')"
python -c "import matplotlib; print('  matplotlib:   OK (core-loop diagram)')"

echo.
echo 如果以上都显示OK,环境就装好了。
echo.
echo 接下来:
echo   1. 首次运行会自动下载PaddleOCR中文模型^(约100MB^),需联网,只下一次
echo   2. 用法见同目录 使用说明.md ^(自己跑^) 或 新会话AI使用说明.md ^(交给AI跑^)
echo.
pause

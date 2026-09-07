@echo off
title 解锁时间线工具
:menu
cls
echo ============================================
echo            解锁时间线工具
echo ============================================
echo.
echo  待分析视频放 videos\ 文件夹（选2/3/4时只输文件名）
echo  分析报告自动输出到 reports\ 文件夹
echo.
echo  [1] 标定新游戏（拖框，一个游戏只做一次）
echo  [2] 分析视频（粗扫2fps，日常使用推荐）
echo  [3] 分析视频（强制细扫30fps，慢、精度最高）
echo  [4] 抽取某时刻画面预览
echo  [5] 生成AI审阅包（AI自动命名用）
echo  [6] 终审出报告（填完 names.json/review_notes.md 后执行；自动附审计+发布reports）
echo  [7] 首末对拍审计+压线清单（漏检对账，可单独重跑）
echo  [8] 环境自检（换电脑部署后先跑这个）
echo  [9] 退出
echo.
set /p choice=请选择:
if "%choice%"=="1" goto calib
if "%choice%"=="2" goto fast
if "%choice%"=="3" goto fine
if "%choice%"=="4" goto frame
if "%choice%"=="5" goto aipack
if "%choice%"=="6" goto final
if "%choice%"=="7" goto audit
if "%choice%"=="8" goto envchk
goto menu

:calib
call :askvideo
if "%video%"=="" goto menu
set /p ts=标定帧时间(mm:ss，留空=自动取中点；推荐人工截图方式见README):
python "%~dp0calibrate.py" "%video%" %ts%
pause
goto menu

:fast
call :askvideo
if "%video%"=="" goto menu
set /p game=输入游戏目录名(games下):
python "%~dp0analyze.py" "%video%" "%~dp0games\%game%"
pause
goto menu

:fine
call :askvideo
if "%video%"=="" goto menu
set /p game=输入游戏目录名(games下):
set /p fpsv=帧率(默认30):
if "%fpsv%"=="" set fpsv=30
python "%~dp0analyze.py" "%video%" "%~dp0games\%game%" --fps %fpsv%
pause
goto menu

:frame
call :askvideo
if "%video%"=="" goto menu
set /p ts=时刻(mm:ss，如06:40):
python "%~dp0sample_frame.py" "%video%" %ts%
pause
goto menu

:aipack
set /p game=输入游戏目录名(games下):
python "%~dp0ai_review.py" "%~dp0games\%game%"
echo 把 ai_review 文件夹发给AI，得到JSON后存为 names.json，再选[6]出报告
pause
goto menu

:final
set /p game=输入游戏目录名(games下):
python "%~dp0finalize.py" "%~dp0games\%game%"
start "" "%~dp0reports\%game%\解锁时间线.md"
pause
goto menu

:audit
set /p game=输入游戏目录名(games下):
python "%~dp0lock_audit.py" "%~dp0games\%game%"
echo 疑似漏检请目检 games\%game%\work\review\audit_start_vs_end.png 裁决
pause
goto menu

:envchk
python "%~dp0check_env.py"
pause
goto menu

rem ---- 输入解析：含\视作完整路径；否则到 videos\ 下找 ----
:askvideo
set "video="
set /p video=输入视频文件名(已放 videos\ 下则只输文件名；也可输完整路径):
if "%video%"=="" goto :eof
echo %video%| findstr /c:"\\" >nul
if not errorlevel 1 goto :eof
if exist "%~dp0videos\%video%" (
    set "video=%~dp0videos\%video%"
) else (
    echo videos\ 下找不到 "%video%"，请先把视频放入 videos\ 文件夹。
    pause
    set "video="
)
goto :eof

# -*- coding: utf-8 -*-
"""环境自检：换电脑部署后先跑我，缺什么一目了然
用法：python check_env.py
检查：Python版本 / opencv-python(含GUI) / numpy / ffmpeg / ffprobe
"""
import sys, subprocess, shutil

OK, BAD = "[OK] ", "[缺] "

print("=" * 46)
print(" 解锁时间线工具 · 环境自检")
print("=" * 46)
problems = []

# 1. Python
v = sys.version_info
if v >= (3, 7):
    print(f"{OK} Python {v.major}.{v.minor}.{v.micro}")
else:
    print(f"{BAD} Python {v.major}.{v.minor} 过老（需>=3.7）"); problems.append("python")

# 2. opencv + numpy
try:
    import cv2
    print(f"{OK} opencv {cv2.__version__}")
    # GUI 能力（selectROI 拖框必需，headless 版没有）
    try:
        cv2.namedWindow("__env_check__")
        cv2.destroyAllWindows()
        print(f"{OK} opencv GUI 可用（能弹拖框窗口）")
    except Exception as ex:
        print(f"{BAD} opencv 无 GUI（装成 headless 版了）：{ex}")
        problems.append("opencv-python 正式版(勿装headless)")
except ImportError:
    print(f"{BAD} 没装 opencv：pip install opencv-python")
    problems.append("opencv-python")

try:
    import numpy
    print(f"{OK} numpy {numpy.__version__}")
except ImportError:
    print(f"{BAD} 没装 numpy：pip install numpy")
    problems.append("numpy")

# 3. ffmpeg / ffprobe
for tool in ("ffmpeg", "ffprobe"):
    p = shutil.which(tool)
    if p:
        try:
            r = subprocess.run([tool, "-version"], capture_output=True, text=True, timeout=10)
            first = (r.stdout or r.stderr).splitlines()[0][:60]
            print(f"{OK} {tool}: {first}")
        except Exception as ex:
            print(f"{BAD} {tool} 无法执行：{ex}")
            problems.append(tool)
    else:
        print(f"{BAD} {tool} 不在 PATH（抽帧/精化全靠它）")
        problems.append(f"{tool} 加入PATH")

print("=" * 46)
if problems:
    print("缺少依赖：", "、".join(problems))
    print("装法：")
    print("  pip install opencv-python numpy")
    print("  ffmpeg：winget install Gyan.FFmpeg  （或官网下包后把 bin 加进 PATH）")
    print("  装完重开命令行再跑一次本自检。")
else:
    print("环境完备！双击 开始分析.bat 或按 README 步骤开工。")

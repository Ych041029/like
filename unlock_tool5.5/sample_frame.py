# -*- coding: utf-8 -*-
"""按 mm:ss 从视频抽一帧预览（人工挑干净帧用）
用法：python sample_frame.py <视频> [mm:ss] [输出名]
"""
import subprocess, os, sys

v = sys.argv[1]
ts = sys.argv[2] if len(sys.argv) > 2 else None
out = sys.argv[3] if len(sys.argv) > 3 else "_sample.png"
cmd = ["ffmpeg", "-v", "error", "-y"]
if ts:
    cmd += ["-ss", f"{int(ts.split(':')[0]):02d}:{int(ts.split(':')[1]):02d}"]
cmd += ["-i", v, "-frames:v", "1", out]
subprocess.run(cmd, check=True)
print("saved:", os.path.abspath(out))

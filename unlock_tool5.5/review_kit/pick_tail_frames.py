# -*- coding: utf-8 -*-
"""标定候选帧选取：从视频指定区间均匀抽 N 帧（烧录时间戳）供 AI 挑选干净帧
用法：python pick_tail_frames.py <视频> <输出目录> [数量=6] [起点占比=0.7] [终点占比=1.0]
"""
import os, sys, subprocess

video = sys.argv[1]
outdir = sys.argv[2]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 6
p0 = float(sys.argv[4]) if len(sys.argv) > 4 else 0.7
p1 = float(sys.argv[5]) if len(sys.argv) > 5 else 1.0

dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "csv=p=0", video], capture_output=True, text=True)
dur = float(dur.stdout.strip())
os.makedirs(outdir, exist_ok=True)

times = [dur * (p0 + (p1 - p0) * i / max(1, n - 1)) for i in range(n)]
for i, t in enumerate(times, 1):
    m, s = divmod(t, 60)
    out = os.path.join(outdir, f"cand{i:02d}_{int(m):02d}m{int(s):02d}s.png")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", video,
                    "-frames:v", "1", out], check=True)
    print(f"cand{i:02d}: {int(m):02d}:{int(s):02d} -> {out}")
print(f"[pick] {n} 张候选帧已存 {outdir}（AI 逐张目检挑最干净的一帧做标定提案）")

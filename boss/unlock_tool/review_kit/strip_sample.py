# -*- coding: utf-8 -*-
"""按时间抽样某ROI裁图拼成时间轴（人工核对UI元素演变的利器）
用法：python strip_sample.py <游戏目录> <x,y,w,h> <秒1,秒2,...> [列数]
输出：work/review/timeline_x{x}_y{y}.png
依赖：<游戏目录>/work/frames 下的2fps抽帧（analyze.py 产物）
"""
import cv2, os, sys
import numpy as np

def imread_u(path):
    try:
        return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return cv2.imread(path)

gdir = sys.argv[1]
roi = [int(x) for x in sys.argv[2].split(",")]
times = [float(x) for x in sys.argv[3].split(",")]
cols = int(sys.argv[4]) if len(sys.argv) > 4 else len(times)
x, y, w, h = roi
fdir = os.path.join(gdir, "work", "frames")
files = sorted(f for f in os.listdir(fdir) if f.endswith(".png"))

rows = []
for t in times:
    i = min(len(files) - 1, int(t * 2))
    im = imread_u(os.path.join(fdir, files[i]))
    crop = im[y:y+h, x:x+w]
    sc = 2
    crop = cv2.resize(crop, (w*sc, h*sc), interpolation=cv2.INTER_NEAREST)
    row = np.full((crop.shape[0] + 20, crop.shape[1] + 8, 3), 24, np.uint8)
    cv2.putText(row, f"{int(t)//60:02d}:{int(t)%60:02d}", (2, 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 255, 255), 1)
    row[16:16+crop.shape[0], 4:4+crop.shape[1]] = crop
    rows.append(row)

H = max(r.shape[0] for r in rows)
W = max(r.shape[1] for r in rows)
nrows = (len(rows) + cols - 1) // cols
sheet = np.full((nrows * (H + 4), (W + 4) * cols, 3), 24, np.uint8)
for i, r in enumerate(rows):
    rr, cc = divmod(i, cols)
    sheet[rr*(H+4):rr*(H+4)+r.shape[0], cc*(W+4):cc*(W+4)+r.shape[1]] = r
out = os.path.join(gdir, "work", "review", f"timeline_x{x}_y{y}.png")
os.makedirs(os.path.dirname(out), exist_ok=True)
ok, buf = cv2.imencode(".png", sheet)
buf.tofile(out)
print("saved", out)

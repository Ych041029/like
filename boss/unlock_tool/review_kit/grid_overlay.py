# -*- coding: utf-8 -*-
"""坐标网格测量：给帧叠加 20px 网格 + 每100px坐标标注，供 AI 精确读框位置
用法：python grid_overlay.py <帧图> <输出.png> [缩放=2]
"""
import cv2, os, sys
import numpy as np

def imread_u(path):
    try:
        return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return cv2.imread(path)

img = imread_u(sys.argv[1])
out = sys.argv[2]
Z = int(sys.argv[3]) if len(sys.argv) > 3 else 2
H, W = img.shape[:2]
img = cv2.resize(img, (W*Z, H*Z), interpolation=cv2.INTER_NEAREST)

for x in range(0, W+1, 20):
    c = (0, 255, 255) if x % 100 == 0 else (80, 80, 80)
    cv2.line(img, (x*Z, 0), (x*Z, H*Z), c, 1)
    if x % 100 == 0:
        cv2.putText(img, str(x), (x*Z+2, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
for y in range(0, H+1, 20):
    c = (0, 255, 255) if y % 100 == 0 else (80, 80, 80)
    cv2.line(img, (0, y*Z), (W*Z, y*Z), c, 1)
    if y % 100 == 0:
        cv2.putText(img, str(y), (2, y*Z + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)

os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
ok, buf = cv2.imencode(".png", img)
buf.tofile(out)
print("saved:", out)

# -*- coding: utf-8 -*-
"""标定提案渲染器：把 AI 提议的框画到帧上，生成给人工确认的示意图
用法1：python render_boxes.py <帧图> <提案.json> <输出.png> [缩放=2]
用法2：python render_boxes.py <2x网格底图> <提案.json> <输出.png> --base2x [只渲染某类]
提案.json：{"title":..., "activity":[[x,y,w,h]..], "nav":[[..]..],
            "cultivation":[[..]..], "only": "activity"}
"""
import cv2, os, sys, json
import numpy as np

args = [a for a in sys.argv[1:] if a != "--base2x"]
BASE2X = "--base2x" in sys.argv
frame_p, prop_p, out_p = args[0], args[1], args[2]
ZOOM = int(args[3]) if len(args) > 3 else 2
ONLY = args[4] if len(args) > 4 else None

def imread_u(path):
    try:
        return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return cv2.imread(path)

img = imread_u(frame_p)
prop = json.load(open(prop_p, encoding="utf-8"))
H, W = img.shape[:2]
Z = 2 if BASE2X else ZOOM
if not BASE2X:
    img = cv2.resize(img, (W*Z, H*Z), interpolation=cv2.INTER_NEAREST)
TH = max(1, Z // 2 + 1)

CATS = [("activity", (0, 0, 255), "ACT"), ("nav", (0, 220, 220), "NAV"),
        ("cultivation", (255, 0, 255), "CULT")]
legend = [f"{prop.get('title', 'AI calibration proposal')}  |  "]
for cat, color, zh in CATS:
    if ONLY and cat != ONLY:
        continue
    boxes = prop.get(cat, [])
    for i, (x, y, w, h) in enumerate(boxes, 1):
        cv2.rectangle(img, (x*Z, y*Z), ((x+w)*Z, (y+h)*Z), color, TH)
        cv2.putText(img, f"{cat[:3]}{i}", (x*Z+2, (y+2)*Z),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4 + 0.3*max(1, Z//2), color, 1)
    legend.append(f"{zh}({cat})x{len(boxes)}  ")

banner_h = 30 * max(1, Z // 2)
canvas = np.full((img.shape[0] + banner_h, img.shape[1], 3), 20, np.uint8)
cv2.putText(canvas, "".join(legend), (8, banner_h - 10),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55 * max(1, Z // 2), (0, 255, 0), 1)
canvas[banner_h:, :] = img

os.makedirs(os.path.dirname(os.path.abspath(out_p)), exist_ok=True)
ok, buf = cv2.imencode(".png", canvas)
buf.tofile(out_p)
print("saved:", out_p)

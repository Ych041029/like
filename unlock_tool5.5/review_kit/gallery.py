# -*- coding: utf-8 -*-
"""状态图廊：某追踪区全部事件的 a 帧按时间排成网格，检验图标集合是否变化"""
import cv2, os, sys, json
import numpy as np

def imread_u(path):
    try:
        return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return cv2.imread(path)

gdir = sys.argv[1]
rid = sys.argv[2]
CELLH = int(sys.argv[3]) if len(sys.argv) > 3 else 110
PERROW = 20

tl = json.load(open(os.path.join(gdir, "work", "timeline.json"), encoding="utf-8"))
evs = sorted((e for e in tl["events"] if e["id"] == rid), key=lambda e: e["t"])
evd = os.path.join(gdir, "work", "ev")

cells = []
for e in evs:
    a = imread_u(os.path.join(evd, os.path.basename(e["ev"]) + "_a.png"))
    if a is None: continue
    h, w = a.shape[:2]
    nw = max(1, int(w * CELLH / h))
    cells.append((e["t_disp"], cv2.resize(a, (nw, CELLH), interpolation=cv2.INTER_NEAREST)))

if not cells:
    raise SystemExit("no cells")
CW = max(c[1].shape[1] for c in cells) + 2
nrows = (len(cells) + PERROW - 1) // PERROW
sheet = np.full((nrows * (CELLH + 18), PERROW * CW, 3), 24, np.uint8)
for i, (t, im) in enumerate(cells):
    r, c = divmod(i, PERROW)
    y0 = r * (CELLH + 18)
    cv2.putText(sheet, t, (c * CW + 1, y0 + 11), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (0, 255, 255), 1)
    sheet[y0 + 14:y0 + 14 + CELLH, c * CW:c * CW + im.shape[1]] = im

out = os.path.join(gdir, "work", "review", f"gallery_{rid}.png")
ok, buf = cv2.imencode(".png", sheet)
buf.tofile(out)
print("saved", out, f"{len(cells)} cells, {nrows} rows")

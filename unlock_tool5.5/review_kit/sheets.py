# -*- coding: utf-8 -*-
"""证据对照表生成器：把事件的 b/a 帧对拼成大图供批量目检
用法：
  python _sheets.py <gdir> <输出名> <行高> --id <追踪区id>     # 该区全部事件按时间序
  python _sheets.py <gdir> <输出名> <行高> <tag1> <tag2> ...   # 指定事件
"""
import cv2, os, sys, json
import numpy as np

def imread_u(path):
    try:
        return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return cv2.imread(path)

gdir = sys.argv[1]
outname = sys.argv[2]
ROWH = int(sys.argv[3])
args = sys.argv[4:]

evd = os.path.join(gdir, "work", "ev")
tl = json.load(open(os.path.join(gdir, "work", "timeline.json"), encoding="utf-8"))
meta = {e["ev"]: e for e in tl["events"] if e.get("ev")}

if args[0] == "--id":              # 该追踪区的全部事件按时间序
    rid = args[1]
    pairs = [(e["ev"], e["ev"]) for e in sorted(
        (e for e in tl["events"] if e["id"] == rid), key=lambda e: e["t"])]
else:
    pairs = [(t, t) for t in args]

LW = 168
rows = []
for label, tag in pairs:
    b = imread_u(os.path.join(evd, os.path.basename(tag) + "_b.png"))
    a = imread_u(os.path.join(evd, os.path.basename(tag) + "_a.png"))
    if b is None or a is None:
        print("missing:", tag); continue
    e = meta.get("ev/" + os.path.basename(tag), {})
    def rs(im):
        h, w = im.shape[:2]
        nw = max(1, int(w * ROWH / h))
        return cv2.resize(im, (nw, ROWH), interpolation=cv2.INTER_NEAREST)
    b, a = rs(b), rs(a)
    lab = f"{e.get('t_disp','?')} {e.get('t_precise','')} h{e.get('ham','?')} s{e.get('dsat','?'):+}"
    row = np.full((ROWH + 16, LW + b.shape[1] + a.shape[1] + 12, 3), 24, np.uint8)
    cv2.putText(row, os.path.basename(tag), (2, 11), cv2.FONT_HERSHEY_SIMPLEX, 0.34, (0, 255, 255), 1)
    cv2.putText(row, lab, (2, ROWH + 13), cv2.FONT_HERSHEY_SIMPLEX, 0.34, (255, 255, 255), 1)
    row[8:8+ROWH, LW:LW+b.shape[1]] = b
    row[8:8+ROWH, LW+b.shape[1]+4:LW+b.shape[1]+4+a.shape[1]] = a
    rows.append(row)

if not rows:
    raise SystemExit("no rows")
H = max(r.shape[0] for r in rows)
W = max(r.shape[1] for r in rows)
PER = max(1, int(2200 / H))
sheets = [rows[i:i+PER] for i in range(0, len(rows), PER)]
odir = os.path.join(gdir, "work", "review")
os.makedirs(odir, exist_ok=True)
for si, chunk in enumerate(sheets):
    sh = np.full(((H + 2) * len(chunk), W, 3), 24, np.uint8)
    for ri, r in enumerate(chunk):
        sh[ri*(H+2):ri*(H+2)+r.shape[0], :r.shape[1]] = r
    out = os.path.join(odir, f"{outname}_{si+1:02d}.png")
    ok, buf = cv2.imencode(".png", sh)
    buf.tofile(out)
    print("saved", out, f"({len(chunk)} rows)")

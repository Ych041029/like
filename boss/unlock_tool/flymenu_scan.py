# -*- coding: utf-8 -*-
"""飞出菜单·通用清点器（游戏无关版）
前置（每游戏一次性标定，见 AI工作手册 §9.9）：
  1. config.json 含 gate_roi 与 anchors（解锁时间线任务已有）；
  2. games/<游戏>/flymenu_tpl/ 下放菜单模板 png——必须裁自"菜单确实在场"的帧，
     同一菜单的不同 UI 状态（如红点/无红点）各存一张，命名 <菜单组>_<状态>.png，
     分组名取"_"前缀（同组=同一种菜单的不同状态）；
  3. 可选 index.json：{"<模板名>": {"box":[x,y,w,h], "th":0.90}}，box=该菜单在
     全帧中的出现区域（用于位置过滤假阳性），th=该模板的命中阈值（默认0.85）。
逻辑：全帧（含门控拒绝帧）半尺度模板匹配 → 每模板逐帧 开/关 状态序列 →
  上升沿计数=点击次数，连续段=每次打开区间 → 片尾状态检查。
输出：games/<游戏>/work/flymenu/scan_result.json + 命中区间表。

用法：python flymenu_scan.py <视频> <游戏目录> [th=0.85]
"""
import cv2, os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import imread_u, classify_refs, dhash, ham, fmtt

TH_DEF = float(sys.argv[3]) if len(sys.argv) > 3 else 0.85
video, gdir = sys.argv[1], sys.argv[2]
FPS = 2
wdir = os.path.join(gdir, "work")
fdir = os.path.join(wdir, "frames")
files = sorted(f for f in os.listdir(fdir) if f.endswith(".png"))
cfg = json.load(open(os.path.join(gdir, "config.json"), encoding="utf-8"))
gate = tuple(cfg["gate_roi"])
refs, Vref = classify_refs(fdir, files, cfg.get("anchors", {}), gate=gate)
N = len(files)

tdir = os.path.join(gdir, "flymenu_tpl")
tpls = []
for fn in sorted(os.listdir(tdir)):
    if not fn.lower().endswith(".png"):
        continue
    name = fn[:-4]
    im = imread_u(os.path.join(tdir, fn))
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, (g.shape[1] // 2, g.shape[0] // 2), interpolation=cv2.INTER_AREA)
    idxp = os.path.join(tdir, name + ".json")
    box, th = None, TH_DEF
    if os.path.exists(idxp):
        j = json.load(open(idxp, encoding="utf-8"))
        box = j.get("box")
        th = float(j.get("th", TH_DEF))
    group = name.split("_")[0]
    tpls.append(dict(name=name, group=group, tpl=g, box=box, th=th))
if not tpls:
    raise SystemExit("flymenu_tpl 下没有模板，请先目检确认菜单后剪模板")
print(f"[模板] {len(tpls)} 张：" + "、".join(t['name'] for t in tpls))

# ---- 全帧扫描（含门控拒绝帧：菜单压暗主页时门控会误拒，此处必须全扫）----
state = {t["name"]: [False] * N for t in tpls}
scores = {t["name"]: [0.0] * N for t in tpls}
for fi in range(N):
    im = imread_u(os.path.join(fdir, files[fi]))
    if im is None:
        continue
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    g2 = cv2.resize(g, (g.shape[1] // 2, g.shape[0] // 2),
                    interpolation=cv2.INTER_AREA)
    for t in tpls:
        res = cv2.matchTemplate(g2, t["tpl"], cv2.TM_CCOEFF_NORMED)
        mn, mx, mnl, mxl = cv2.minMaxLoc(res)
        scores[t["name"]][fi] = mx
        ok = mx >= t["th"]
        if ok and t["box"]:
            x, y, w, h = t["box"]
            ok = (abs(mxl[0] * 2 - x) <= 60 and abs(mxl[1] * 2 - y) <= 60)
        state[t["name"]][fi] = bool(ok)

# ---- 上升沿计数 + 连续段归并（间隙≤3帧视为同一次打开）----
def runs_of(state):
    out, st = [], None
    for i, v in enumerate(state):
        if v and st is None:
            st = i
        elif not v and st is not None:
            out.append([st, i - 1])
            st = None
    if st is not None:
        out.append([st, N - 1])
    merged = []
    for r in out:
        if merged and r[0] - merged[-1][1] <= 3:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return merged

print("=== 点击清点（上升沿=一次点击）===")
result = {}
total = 0
for t in tpls:
    rs = runs_of(state[t["name"]])
    result[t["name"]] = [dict(start=a, end=b,
                              t_start=fmtt(a / FPS), t_end=fmtt(b / FPS))
                         for a, b in rs]
    total += len(rs)
    print(f"[{t['name']}] 打开 {len(rs)} 次")
    for a, b in rs:
        print(f"   {a//2//60:02d}:{a/2%60:04.1f} ~ {b//2//60:02d}:{b/2%60:04.1f}")

# ---- 片尾状态检查（片尾还开着的菜单必须被记录）----
tail = [t["name"] for t in tpls if state[t["name"]][-1]]
print("片尾仍展开的菜单:", tail if tail else "无")

os.makedirs(os.path.join(wdir, "flymenu"), exist_ok=True)
json.dump(dict(params=dict(th=TH_DEF, half_scale=True, all_frames=True),
               tail_open=tail, opens=result),
          open(os.path.join(wdir, "flymenu", "scan_result.json"), "w",
               encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"合计打开 {total} 次 ->", os.path.join(wdir, "flymenu", "scan_result.json"))
print("注意：相似面板假阳性（如同类UI的标签列）需 AI 目检定性后剔除。")

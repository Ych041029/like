# -*- coding: utf-8 -*-
"""飞出菜单全量扫查（v4·深色面板版，2026-09-02）
原理：本游戏飞出菜单=深色半透明面板（黑底白字条目）。对每个主页帧做
"暗像素连通域"检测（面积≥MIN_AREA，无上限），跨帧归并成实例，输出裁图供AI读文字。
解锁警觉规则：图标未解锁不可点击——实例的锚定图标按 config rois+解锁时间线标注，
解锁前的时间窗内不应出现对应菜单（校验用）。

用法：python flymenu_sweep.py <视频> <游戏目录> [V_th=90] [min_area=3000]
产出：games/<游戏>/work/flymenu/sweep_{candidates.json, crop_*.png, sheet_*.png}
"""
import cv2, os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import imread_u, classify_refs, dhash, ham, fmtt

V_TH = int(sys.argv[3]) if len(sys.argv) > 3 else 90
MIN_AREA = int(sys.argv[4]) if len(sys.argv) > 4 else 3000
CALIB = "--calib" in sys.argv

video, gdir = sys.argv[1], sys.argv[2]
cfg = json.load(open(os.path.join(gdir, "config.json"), encoding="utf-8"))
FPS = 2
wdir = os.path.join(gdir, "work")
fdir = os.path.join(wdir, "frames")
files = sorted(f for f in os.listdir(fdir) if f.endswith(".png"))
gate = tuple(cfg["gate_roi"])
refs, Vref = classify_refs(fdir, files, cfg.get("anchors", {}), gate=gate)
H, W = imread_u(os.path.join(fdir, files[0])).shape[:2]
print(f"[L1] {len(files)} 帧，暗像素阈 V<{V_TH}，最小面积 {MIN_AREA}px²（无上限）")

mains = []
for i, fn in enumerate(files):
    im = imread_u(os.path.join(fdir, fn))
    if im is None:
        continue
    gimg = im[gate[1]:gate[1]+gate[3], gate[0]:gate[0]+gate[2]]
    if min(ham(dhash(gimg), r) for r in refs) < 22:
        Vnow = float(cv2.cvtColor(gimg, cv2.COLOR_BGR2HSV)[:, :, 2].mean())
        if Vref and Vnow < 0.85 * Vref:
            continue
        Vref = 0.95 * Vref + 0.05 * Vnow
    else:
        continue
    mains.append((i, im))

if CALIB:
    k = next(j for j, (i, im) in enumerate(mains) if i == 1408)   # 11:44 玩法菜单帧
    menu = cv2.cvtColor(mains[k][1][262:720, 300:430], cv2.COLOR_BGR2HSV)[:, :, 2]
    battle = cv2.cvtColor(mains[k][1][200:500, 100:300], cv2.COLOR_BGR2HSV)[:, :, 2]
    navw = cv2.cvtColor(mains[k][1][801:820, 0:432], cv2.COLOR_BGR2HSV)[:, :, 2]
    print(f"[实测] 玩法菜单面板V: p50={np.percentile(menu,50):.0f} "
          f"p75={np.percentile(menu,75):.0f}｜战斗区V p50={np.percentile(battle,50):.0f}"
          f"｜导航木条V p50={np.percentile(navw,50):.0f}")

cands = []
for i, im in mains:
    V = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)[:, :, 2]
    dark = (V < V_TH).astype(np.uint8)
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(dark, connectivity=8)
    for j in range(1, n):
        area = int(stats[j, cv2.CC_STAT_AREA])
        if area < MIN_AREA:
            continue
        px, py = int(stats[j, cv2.CC_STAT_LEFT]), int(stats[j, cv2.CC_STAT_TOP])
        pw, ph = int(stats[j, cv2.CC_STAT_WIDTH]), int(stats[j, cv2.CC_STAT_HEIGHT])
        cands.append(dict(fi=i, t=fmtt(i / FPS), box=[px, py, pw, ph],
                          area=area, area_pct=round(area / (W * H) * 100, 2),
                          meanV=round(float(V[py:py+ph, px:px+pw].mean()), 1)))

# 跨帧归并（相邻帧、位置重叠）
cands.sort(key=lambda c: (c["fi"], c["box"][0]))
insts = []
for c in cands:
    hit = None
    for it in insts:
        lc = it["cands"][-1]
        ox = max(0, min(lc["box"][0]+lc["box"][2], c["box"][0]+c["box"][2]) -
                 max(lc["box"][0], c["box"][0]))
        oy = max(0, min(lc["box"][1]+lc["box"][3], c["box"][1]+c["box"][3]) -
                 max(lc["box"][1], c["box"][1]))
        if 0 <= c["fi"] - lc["fi"] <= 1 and ox > 0 and oy > 0:
            hit = it
            break
    if hit:
        hit["cands"].append(c)
        hit["t_end"] = c["t"]
    else:
        insts.append(dict(t_start=c["t"], t_end=c["t"], cands=[c]))

print(f"[L4] 暗色组件 {len(cands)} 个，归并实例 {len(insts)} 个")
for it in insts:
    c = max(it["cands"], key=lambda x: x["area"])
    it["peak"] = c
    it["n_frames"] = len(it["cands"])
    print(f"  {it['t_start']}~{it['t_end']} 持{it['n_frames']}帧 box={c['box']} "
          f"占屏{c['area_pct']:5.2f}% meanV={c['meanV']}")

odir = os.path.join(wdir, "flymenu")
os.makedirs(odir, exist_ok=True)
json.dump(dict(params=dict(V_th=V_TH, min_area=MIN_AREA), instances=insts),
          open(os.path.join(odir, "sweep_candidates.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

# 实例裁图（读文字用，4x）
for n, it in enumerate(insts):
    c = it["peak"]
    px, py, pw, ph = c["box"]
    im = it["cands"][0]  # 占位
    imf = imread_u(os.path.join(fdir, files[c["fi"]]))
    crop = imf[max(0,py-8):min(H,py+ph+8), max(0,px-8):min(W,px+pw+8)]
    z = max(1, min(4, 900 // max(1, max(crop.shape[:2]) // 100)))
    z = max(z, 2)
    crop = cv2.resize(crop, (crop.shape[1] * z, crop.shape[0] * z),
                      interpolation=cv2.INTER_NEAREST)
    cv2.putText(crop, f"#{n+1} {it['t_start']}~{it['t_end']} n{it['n_frames']}",
                (4, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1)
    p = os.path.join(odir, f"crop_{n+1:02d}.png")
    ok, buf = cv2.imencode(".png", crop)
    buf.tofile(p)
print(f"裁图 {len(insts)} 张 -> {odir}\\crop_*.png")

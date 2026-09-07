# -*- coding: utf-8 -*-
"""飞出菜单·模板匹配全量清点（v5，2026-09-02）
用已确认的菜单截图做模板，在全部主页帧上 matchTemplate：
  模板A：挑战玩法菜单（9条目，f_01408）
  模板B：活动菜单（3条目，f_01544）
每次命中=一次菜单打开。另输出每实例的最高分帧号供裁图读文字。
用法：python flymenu_template.py
"""
import cv2, os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import imread_u, classify_refs, dhash, ham, fmtt

gdir = "games/灵画师"
cfg = json.load(open(os.path.join(gdir, "config.json"), encoding="utf-8"))
FPS = 2
wdir = os.path.join(gdir, "work")
fdir = os.path.join(wdir, "frames")
files = sorted(f for f in os.listdir(fdir) if f.endswith(".png"))
gate = tuple(cfg["gate_roi"])
refs, Vref = classify_refs(fdir, files, cfg.get("anchors", {}), gate=gate)

TEMPLATES = {
    "A_挑战玩法菜单": ("games/灵画师/work/frames/f_01408.png", (296, 258, 138, 466)),
    "B_活动菜单":     ("games/灵画师/work/frames/f_01544.png", (296, 211, 84, 214)),
}
templates = {}
for name, (src, (x, y, w, h)) in TEMPLATES.items():
    im = imread_u(src)
    templates[name] = cv2.cvtColor(im[y:y+h, x:x+w], cv2.COLOR_BGR2GRAY)

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
    mains.append((i, cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)))
print(f"[L1] 主页帧 {len(mains)}")

TH_SCORE = 0.72
hits = []
for name, tpl in templates.items():
    th, tw = tpl.shape
    for i, g in mains:
        res = cv2.matchTemplate(g, tpl, cv2.TM_CCOEFF_NORMED)
        mn, mx, mnl, mxl = cv2.minMaxLoc(res)
        if mx >= TH_SCORE:
            hits.append(dict(menu=name, fi=i, t=fmtt(i / FPS),
                             score=round(mx, 3), box=[mxl[0], mxl[1], tw, th]))

hits.sort(key=lambda h: (h["fi"], h["menu"]))
print(f"命中 {len(hits)} 帧·次（阈值 {TH_SCORE}）")
insts = []
for h in hits:
    hit = None
    for it in insts:
        if h["menu"] == it["menu"] and 0 <= h["fi"] - it["hits"][-1]["fi"] <= 1:
            hit = it
            break
    if hit:
        hit["hits"].append(h)
        hit["t_end"] = h["t"]
    else:
        insts.append(dict(menu=h["menu"], t_start=h["t"], t_end=h["t"],
                          hits=[h], score_max=h["score"]))
print(f"归并实例 {len(insts)} 个：")
for n, it in enumerate(insts):
    best = max(it["hits"], key=lambda x: x["score"])
    print(f"  #{n+1} {it['menu']}  {it['t_start']}~{it['t_end']} 持{len(it['hits'])}帧 "
          f"score={it['score_max']} box={best['box']}")

odir = os.path.join(wdir, "flymenu")
json.dump(dict(params=dict(threshold=TH_SCORE), instances=insts),
          open(os.path.join(odir, "template_hits.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
for n, it in enumerate(insts):
    best = max(it["hits"], key=lambda x: x["score"])
    im = imread_u(os.path.join(fdir, files[best["fi"]]))
    x, y, w, h = best["box"]
    crop = im[max(0,y-10):min(820,y+h+10), max(0,x-10):min(432,x+w+10)]
    z = max(1, int(np.ceil(900 / max(crop.shape[:2]))))
    crop = cv2.resize(crop, (crop.shape[1]*z, crop.shape[0]*z),
                      interpolation=cv2.INTER_NEAREST)
    cv2.putText(crop, f"#{n+1} {it['t_start']}~{it['t_end']} score={it['score_max']}",
                (4, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1)
    p = os.path.join(odir, f"tpl_{n+1:02d}.png")
    ok, buf = cv2.imencode(".png", crop)
    buf.tofile(p)
print("裁图 ->", odir, "\\tpl_*.png")

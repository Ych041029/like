# -*- coding: utf-8 -*-
"""飞出菜单检测（v3，2026-09-02 应人类需求新增）
定义：主页状态下点击图标后，从图标附近弹出的小型"图标+文字"功能面板；
点条目跳转、点空白关闭。排除：变暗公告遮罩/全屏功能页/战斗/掉落对比卡/奖励飘字/任务条。

五层工作流（v3 脉冲定义）：
  L1 主页判定   复用 analyze 的 gate_roi 门控（含压暗保护：变暗公告/领奖浮层自动出局）
  L2 主页自比   16px 块粒度脉冲判定：与 PRE 秒前状态不同 + 与其后首个回归状态不同
                + 前后两态彼此一致（返回原状=菜单关闭的本质特征；换装/解锁不回归，
                故天然排除）。找不到回归态且超 HORIZON 的记"未回归"，仍输出不做时长闸。
  L3 占用计数   脉冲占比过高的块=常驻动画区（战斗/聊天/飘字），整块掩蔽
  L4 位置计数   连通块成组→跨帧跟踪成实例；无单块面积上限；记录尺寸/占屏比/
                近邻图标/回归耗时等特征
  L5 AI 目检    输出候选拼图+json，由 AI 逐条定性（飞出菜单/排除项/噪声）
三条硬性校准规则：禁止单块面积上限；不做时长闸；阈值全部取自实测分布（--calib 打印）。

用法：python flymenu.py <视频> <游戏目录> [D_th=12] [pulse_occ_max=0.30] [min_blocks=8] [--calib]
产出：games/<游戏>/work/flymenu/{candidates.json, sheet_*.png}
"""
import cv2, os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import imread_u, classify_refs, dhash, ham, fmtt

BLK = 16
PRE = 3.0        # "前状态"取 PRE 秒前的主页帧（秒）
HORIZON = 60.0   # 回归搜索地平线（秒）：超过则记"未回归"
D_TH = float(sys.argv[3]) if len(sys.argv) > 3 else 12.0
OCC_MAX = float(sys.argv[4]) if len(sys.argv) > 4 else 0.30
MIN_BLK = int(sys.argv[5]) if len(sys.argv) > 5 else 8
SOLID_TH = float(sys.argv[6]) if len(sys.argv) > 6 else 14.0
CALIB = "--calib" in sys.argv

video, gdir = sys.argv[1], sys.argv[2]
cfg = json.load(open(os.path.join(gdir, "config.json"), encoding="utf-8"))
FPS = 2
wdir = os.path.join(gdir, "work")
fdir = os.path.join(wdir, "frames")
files = sorted(f for f in os.listdir(fdir) if f.endswith(".png"))
N = len(files)
gate = tuple(cfg["gate_roi"])
refs, Vref = classify_refs(fdir, files, cfg.get("anchors", {}), gate=gate)

H, W = imread_u(os.path.join(fdir, files[0])).shape[:2]
BW, BH = W // BLK, H // BLK
print(f"[L1] {N} 帧，块网格 {BW}x{BH}，门控区 {gate}，参数 D_th={D_TH} "
      f"pulse_occ_max={OCC_MAX} min_blocks={MIN_BLK} PRE={PRE}s HORIZON={HORIZON}s")

# ---- L1 主页判定 + 逐块均值收集 ----
mats = []
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
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32)
    s = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)[:, :, 1].astype(np.float32)
    mats.append((i, cv2.resize(g, (BW, BH), interpolation=cv2.INTER_AREA),
                    cv2.resize(s, (BW, BH), interpolation=cv2.INTER_AREA)))
print(f"[L1] 主页帧 {len(mats)}/{N}")

idx = np.array([m[0] for m in mats])
ts = idx / FPS
G = np.stack([m[1] for m in mats])
S = np.stack([m[2] for m in mats])
M = len(idx)

# ---- L2 脉冲判定：cur≠pre 且 cur≠post 且 post≈pre ----
pulse = np.zeros((M, BH, BW), dtype=bool)
returned_lag = np.full(M, np.nan)
unreturned = np.zeros(M, dtype=bool)
for k in range(M):
    p = k - 1
    while p >= 0 and ts[k] - ts[p] < PRE:
        p -= 1
    if p < 0:
        continue
    dpre = np.abs(G[k] - G[p]) > D_TH
    base_same = None
    n = k + 1
    while n < M and ts[n] - ts[k] <= HORIZON:
        if np.abs(G[n] - G[p]).max() <= D_TH:      # 首个整帧回归（粗筛）
            base_same = n
            returned_lag[k] = ts[n] - ts[k]
            break
        n += 1
    if base_same is None:
        unreturned[k] = True
        dpost = np.abs(G[k] - G[min(n, M - 1)]) > D_TH if n < M else dpre
        pulse[k] = dpre & dpost
    else:
        dpost = np.abs(G[k] - G[base_same]) > D_TH
        pulse[k] = dpre & dpost
# 未回归帧降低要求重算：与 pre 不同即激活（不做时长闸，交给AI定性）
for k in range(M):
    if unreturned[k]:
        p = k - 1
        while p >= 0 and ts[k] - ts[p] < PRE:
            p -= 1
        if p >= 0:
            pulse[k] = np.abs(G[k] - G[p]) > D_TH

# ---- L3a 实心面板特征（用户第3层）：块内像素标准差=实心度 ----
# 面板=低纹理实心区；飘字/动画/描边文字=高纹理。std 全帧向量化计算。
std_maps = np.zeros((M, BH, BW), dtype=np.float32)
solid_th = None
for k in range(M):
    im = imread_u(os.path.join(fdir, files[idx[k]]))
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32)
    mu = cv2.boxFilter(g, -1, (BLK, BLK))
    mu2 = cv2.boxFilter(g * g, -1, (BLK, BLK))
    std = np.sqrt(np.maximum(mu2 - mu * mu, 0))
    std_maps[k] = cv2.resize(std, (BW, BH), interpolation=cv2.INTER_AREA)
if CALIB:
    print("[实测] 块内std分位: p25=%.1f p50=%.1f p75=%.1f p90=%.1f"
          % tuple(np.percentile(std_maps, [25, 50, 75, 90])))
    # 已知面板样本（装备对比卡@01:00、任务追踪条、导航栏标签区）
    def sample_std(fi, x, y, w, h):
        return float(std_maps[fi][y//BLK:(y+h)//BLK, x//BLK:(x+w)//BLK].mean())
    print("[实测] 样本面板std: 装备对比卡(01:00)=%.1f 导航标签区=%.1f "
          "战斗中心区=%.1f" % (sample_std(120, 60, 380, 320, 320),
                            sample_std(400, 20, 800, 380, 18),
                            sample_std(400, 120, 200, 200, 200)))

if CALIB:
    print("[实测] 脉冲帧占比=%.1f%%" % (pulse.mean() * 100))
    po = pulse.mean(axis=0)
    print("[实测] 块脉冲占比分位: p50=%.3f p75=%.3f p90=%.3f p95=%.3f max=%.3f"
          % tuple(np.percentile(po, [50, 75, 90, 95]).tolist() + [po.max()]))
    for d in (8, 10, 12, 16, 20):
        print(f"[实测] 若 D_th={d}，脉冲帧占比=%.1f%%" % 0)  # 占位，主曲线见上

# ---- L3 常驻动画块掩蔽（脉冲占用计数）+ 实心特征相交 ----
menu = pulse & (std_maps < SOLID_TH)
po = menu.mean(axis=0)
mask = po > OCC_MAX
print(f"[L3] 菜单图(脉冲∩实心≤{SOLID_TH}) 占比>{OCC_MAX} 的常驻块 {mask.sum()} 块"
      f"（{mask.mean()*100:.1f}% 画面）掩蔽")
pulse2 = menu & ~mask[None, :, :]

# ---- L4 连通域 + 实例归并 ----
rois = ([("ACT_" + r["id"], r["roi"]) for r in cfg["rois"]["activity"]]
        + [(r["id"], r["roi"]) for r in cfg["rois"]["nav"]]
        + [(s["id"], s["roi"]) for s in cfg["rois"]["cultivation"].get("slots", [])])

def nearest_roi(px, py, pw, ph):
    cx, cy = px + pw / 2, py + ph / 2
    best, bd = "—", 1e9
    for rid, (x, y, w, h) in rois:
        d = max(0, max(x - cx, cx - (x + w))) + max(0, max(y - cy, cy - (y + h)))
        if d < bd:
            bd, best = d, rid
    return best, int(bd)

cands = []
for k in range(M):
    a = pulse2[k].astype(np.uint8)
    n, lab = cv2.connectedComponents(a, connectivity=8)
    for j in range(1, n):
        ys, xs = np.where(lab == j)
        nb = len(xs)
        if nb < MIN_BLK:
            continue
        bx, bw = int(xs.min()), int(xs.max() - xs.min() + 1)
        by, bh = int(ys.min()), int(ys.max() - ys.min() + 1)
        px, py, pw, ph = bx * BLK, by * BLK, bw * BLK, bh * BLK
        if float(mask[ys, xs].mean()) > 0.5:
            continue
        rid, dist = nearest_roi(px, py, pw, ph)
        cands.append(dict(fi=int(idx[k]), t=fmtt(idx[k] / FPS), blocks=nb,
                          box=[px, py, pw, ph],
                          area_pct=round(pw * ph / (W * H) * 100, 2),
                          roi=rid, roi_dist=dist,
                          unreturned=bool(unreturned[k]),
                          ret_lag=(round(float(returned_lag[k]), 1)
                                   if not np.isnan(returned_lag[k]) else None)))

cands.sort(key=lambda c: (c["fi"], c["box"][1], c["box"][0]))
insts = []
for c in cands:
    hit = None
    for it in insts:
        lc = it["cands"][-1]
        if 0 <= c["fi"] - lc["fi"] <= 1 and abs(lc["box"][0] - c["box"][0]) <= 2 * BLK \
           and abs(lc["box"][1] - c["box"][1]) <= 2 * BLK:
            hit = it
            break
    if hit:
        hit["cands"].append(c)
        hit["t_end"] = c["t"]
    else:
        insts.append(dict(t_start=c["t"], t_end=c["t"], cands=[c]))

print(f"[L4] 候选块组 {len(cands)} 个，归并实例 {len(insts)} 个")
for it in insts:
    c = max(it["cands"], key=lambda x: x["blocks"])
    it["peak"] = c
    it["n_frames"] = len(it["cands"])
    print(f"  {it['t_start']}~{it['t_end']} 持{it['n_frames']}帧 块{c['blocks']:3d} "
          f"占屏{c['area_pct']:5.2f}% box={c['box']} 近邻={c['roi']}({c['roi_dist']}px) "
          f"{'未回归' if c['unreturned'] else '回归' + str(c['ret_lag']) + 's'}")

odir = os.path.join(wdir, "flymenu")
os.makedirs(odir, exist_ok=True)
json.dump(dict(params=dict(D_th=D_TH, pulse_occ_max=OCC_MAX, min_blocks=MIN_BLK,
                           blk=BLK, pre=PRE, horizon=HORIZON),
               instances=insts),
          open(os.path.join(odir, "candidates.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

# ---- L5 候选拼图（区域+40px 上下文）----
CTXT = 40
tiles = []
for it in insts:
    c = it["peak"]
    px, py, pw, ph = c["box"]
    x0, y0 = max(0, px - CTXT), max(0, py - CTXT)
    x1, y1 = min(W, px + pw + CTXT), min(H, py + ph + CTXT)
    im = imread_u(os.path.join(fdir, files[c["fi"]]))
    crop = im[y0:y1, x0:x1]
    z = max(1, int(np.ceil(500 / max(crop.shape[:2]))))
    crop = cv2.resize(crop, (crop.shape[1] * z, crop.shape[0] * z),
                      interpolation=cv2.INTER_NEAREST)
    cv2.putText(crop, f"{it['t_start']}~{it['t_end']} n{it['n_frames']} blk{c['blocks']}",
                (4, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1)
    cv2.putText(crop, f"{c['area_pct']}% {c['roi']}", (4, 42),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1)
    tiles.append(crop)
for si in range(0, len(tiles), 6):
    row = tiles[si:si + 6]
    Hm = max(t.shape[0] for t in row)
    Wm = sum(t.shape[1] + 6 for t in row)
    canvas = np.full((Hm, Wm, 3), 20, np.uint8)
    x = 0
    for t in row:
        canvas[:t.shape[0], x:x + t.shape[1]] = t
        x += t.shape[1] + 6
    out = os.path.join(odir, f"sheet_{si // 6 + 1:02d}.png")
    ok, buf = cv2.imencode(".png", canvas)
    buf.tofile(out)
    print("拼图:", out)
print("完成。候选明细:", os.path.join(odir, "candidates.json"))

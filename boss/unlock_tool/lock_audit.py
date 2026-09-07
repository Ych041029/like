# -*- coding: utf-8 -*-
"""锁徽章审计 v2：首末对拍 + 压线事件清单（finalize.py 出报告时自动调用）
run_audit(gdir)        主页首帧 vs 末帧逐区对拍，"变了但账上没事件"=漏检嫌疑
borderline_events(gdir) 列出变化量压报警线±3/|dSat|<5 的边缘事件（须放大复核）
"""
import cv2, os, sys, json
import numpy as np

def imread_u(path):
    try:
        return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return cv2.imread(path)

def dhash(img, size=8):
    g = cv2.cvtColor(cv2.resize(img, (size+1, size)), cv2.COLOR_BGR2GRAY)
    return g[:, 1:] > g[:, :-1]

ham = lambda a, b: int(np.count_nonzero(a != b))

def hue_corr(h1, h2):
    """色相直方图相关性：对'棕变青绿'这类纯变色敏感（dhash 的盲区）"""
    h1h = cv2.calcHist([h1], [0], None, [30], [0, 180])
    h2h = cv2.calcHist([h2], [0], None, [30], [0, 180])
    n1, n2 = h1h.sum() or 1, h2h.sum() or 1
    return float(cv2.compareHist(h1h/n1, h2h/n2, cv2.HISTCMP_CORREL))

def _all_rois(cfg):
    rois = [(it["id"], tuple(it["roi"]), "nav/band") for it in cfg["rois"]["nav"]]
    rois += [(it["id"], tuple(it["roi"]), "band") for it in cfg["rois"]["activity"]]
    return rois

def borderline_events(gdir):
    """压线事件清单：距阈值±3以内或|Δsat|<5 的边缘事件，必须放大复核（手册9.4）"""
    cfg = json.load(open(os.path.join(gdir, "config.json"), encoding="utf-8"))
    rp = os.path.join(gdir, "work", "timeline_raw.json")
    src = rp if os.path.exists(rp) else os.path.join(gdir, "work", "timeline.json")
    tl = json.load(open(src, encoding="utf-8"))
    out = []
    for e in tl["events"]:
        if e["kind"] == "nav":
            thH = 13
        elif e["kind"] == "band":
            thH = 14
        elif e["kind"] == "cultf":
            thH = 16          # 首填语义阈值较严（空剪影→填入）
        else:
            thH = 13          # cultg（灰锁→彩色点亮，同副本面板）
        if abs(e["ham"] - thH) <= 3 or abs(e.get("dsat", 0)) < 5:
            out.append(e)
    print(f"\n[borderline] 压线边缘事件 {len(out)} 条（距阈值±3或|dSat|<5，终审须逐条放大复核）：")
    for e in out:
        print(f"  {os.path.basename(e.get('ev') or e['id'])} {e['t_disp']} {e['id']} "
              f"h{e['ham']} s{e['dsat']:+}")
    return out

def run_audit(gdir):
    cfg = json.load(open(os.path.join(gdir, "config.json"), encoding="utf-8"))
    tl = json.load(open(os.path.join(gdir, "work", "timeline.json"), encoding="utf-8"))
    kept_ids = {e["id"] for e in tl["events"]}
    alias = cfg.get("audit_alias", {})
    def covered(rid):
        return rid in kept_ids or any(k in kept_ids for k in alias.get(rid, []))

    fdir = os.path.join(gdir, "work", "frames")
    files = sorted(f for f in os.listdir(fdir) if f.endswith(".png"))
    gate = cfg.get("gate_roi")
    im0 = imread_u(os.path.join(fdir, files[0]))
    gx, gy, gw, gh = gate if gate else (0, 0, im0.shape[1], im0.shape[0])

    anchors = cfg.get("anchors", {}).get("main", ["0:05"])
    def t2sec(t):
        p = [int(x) for x in t.split(":")]
        return p[-1] + p[-2]*60 + (p[0]*3600 if len(p) > 2 else 0)
    ref_idx = [min(len(files)-1, int(t2sec(a)*2)) for a in anchors]
    refs, Vref = [], []
    for i in ref_idx:
        c = imread_u(os.path.join(fdir, files[i]))[gy:gy+gh, gx:gx+gw]
        refs.append(dhash(c))
        Vref.append(cv2.cvtColor(c, cv2.COLOR_BGR2HSV)[:, :, 2].mean())
    Vref = float(np.mean(Vref))

    first_i = last_i = None
    main_run = 0
    for i, fn in enumerate(files):
        im = imread_u(os.path.join(fdir, fn))
        if im is None: continue
        crop = im[gy:gy+gh, gx:gx+gw]
        is_m = min(ham(dhash(crop), r) for r in refs) < 22 and \
            cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)[:, :, 2].mean() >= 0.85*Vref
        main_run = main_run + 1 if is_m else 0
        if first_i is None and i >= 10 and main_run >= 3:
            first_i = i - 2                # 跳过加载画面，取连续3个主页帧的首个
        if is_m:
            last_i = i
    print(f"\n[audit] 主页首帧 #{first_i} ({first_i/2:.1f}s)  末帧 #{last_i} ({last_i/2:.1f}s)")

    im_a = imread_u(os.path.join(fdir, files[first_i]))
    im_b = imread_u(os.path.join(fdir, files[last_i]))
    flagged, rows_out = [], []
    for rid, (x, y, w, h), kind in _all_rois(cfg):
        ca, cb = im_a[y:y+h, x:x+w], im_b[y:y+h, x:x+w]
        dh, dc = ham(dhash(ca), dhash(cb)), hue_corr(ca, cb)
        sa = cv2.cvtColor(ca, cv2.COLOR_BGR2HSV)[:, :, 1].mean()
        sb = cv2.cvtColor(cb, cv2.COLOR_BGR2HSV)[:, :, 1].mean()
        changed = dh >= 10 or dc < 0.75 or abs(sb-sa) >= 12
        has_ev = covered(rid)
        rows_out.append((rid, kind, dh, dc, sb-sa, changed, has_ev))
        if changed:
            flagged.append((rid, ca, cb))

    print(f"{'区域':<12}{'类型':<8}{'ham':>4}{'色相相关':>9}{'dSat':>7}  变了? 有事件?")
    for rid, kind, dh, dc, ds, ch, he in rows_out:
        mark = "  <-- 疑似漏检!" if (ch and not he) else ""
        print(f"{rid:<12}{kind:<8}{dh:>4}{dc:>9.2f}{ds:>+7.1f}  {'Y' if ch else 'n'}     {'Y' if he else 'n'}{mark}")

    if flagged:
        odir = os.path.join(gdir, "work", "review")
        os.makedirs(odir, exist_ok=True)
        tiles = []
        for rid, ca, cb in flagged:
            pair = np.full((ca.shape[0]+20, ca.shape[1]+cb.shape[1]+8, 3), 24, np.uint8)
            cv2.putText(pair, rid, (2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
            pair[16:16+ca.shape[0], 2:2+ca.shape[1]] = ca
            pair[16:16+cb.shape[0], ca.shape[1]+6:ca.shape[1]+6+cb.shape[1]] = cb
            tiles.append(cv2.resize(pair, (pair.shape[1]*3, pair.shape[0]*3),
                                    interpolation=cv2.INTER_NEAREST))
        sheet = np.full((sum(t.shape[0]+4 for t in tiles),
                         max(t.shape[1] for t in tiles), 3), 24, np.uint8)
        yy = 0
        for t in tiles:
            sheet[yy:yy+t.shape[0], :t.shape[1]] = t
            yy += t.shape[0]+4
        ok, buf = cv2.imencode(".png", sheet)
        out = os.path.join(odir, "audit_start_vs_end.png")
        buf.tofile(out)
        print("首末对照图:", out)
    n_sus = sum(1 for rid, kind, dh, dc, ds, ch, he in rows_out if ch and not he)
    print(f"[audit] {len(flagged)} 区域首末有变化；无事件覆盖的疑似漏检 {n_sus} 个"
          + ("（须目检对照图裁决）" if n_sus else ""))
    return rows_out

if __name__ == "__main__":
    g = sys.argv[1] if len(sys.argv) > 1 else "."
    borderline_events(g)
    run_audit(g)

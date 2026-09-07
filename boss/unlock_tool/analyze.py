# -*- coding: utf-8 -*-
"""通用解锁时间线工具 · 第二步：全量分析
用法：
  python analyze.py <视频> <游戏配置目录> [--fps 2]
产出（写在游戏配置目录下）：
  work/timeline.json     事件与时段原始数据
  report_skeleton.md     时间线报告骨架（名称列留待AI/人工终审）
  ev/*.png               每个事件的前后证据帧裁图
设计要点（对应验证期踩过的坑）：
  1) 场景门控：非主页面帧一律不追踪（战斗/弹窗假信号源头切断）
  2) 双指标：感知哈希 + 饱和度，缺一漏报（换色不变形类解锁靠饱和度抓）
  3) 持久判定：新状态须保持若干帧，闪一下的光效/红点自动过滤
  4) 流式读帧：逐张读取即算即弃，不占大内存
  5) 区间型结果：被遮挡期的解锁输出区间并在报告中标注可加密重扫
  6) 短遮挡强制对比（v2.5，params.short_gap_force，默认关）：非主页1~5帧(≤2.5s)恢复
     主页时，副本面板(nav)图标立即与遮挡前最后主页帧对比，超阈值即入账、不等persist
     ——治"解锁即点击进入、persist被点击动画重置"的漏账（灵画师挑战11:42案例）
"""
import cv2, numpy as np, os, sys, json, subprocess

def imread_u(path, flags=cv2.IMREAD_COLOR):
    """cv2.imread 在 Windows 读不了含中文的路径"""
    try:
        return cv2.imdecode(np.fromfile(path, dtype=np.uint8), flags)
    except Exception:
        return cv2.imread(path, flags)

def imwrite_u(path, img, params=None):
    """cv2.imwrite 在 Windows 写不了含中文的路径（静默失败）"""
    try:
        ext = os.path.splitext(path)[1] or ".png"
        ok, buf = cv2.imencode(ext, img, params or [])
        if ok:
            buf.tofile(path)
        return ok
    except Exception:
        return cv2.imwrite(path, img, params or [])

FPS = 2

# ---------- 配置加载 ----------
def load_cfg(gdir):
    cfg = json.load(open(os.path.join(gdir, "config.json"), encoding="utf-8"))
    tracks = {}
    p = cfg.get("params", {})
    for item in cfg["rois"]["activity"]:
        tracks["ACT_" + item["id"]] = dict(box=item["roi"], kind="band",
                                           thH=p.get("band_thH", 14),
                                           thS=p.get("band_thS", 20),
                                           persist=max(2, round(p.get("band_persist", 2.0) * FPS)))
    for item in cfg["rois"]["nav"]:
        tracks[item["id"]] = dict(box=item["roi"], kind="nav", thH=13, thS=18, persist=max(2, round(1.5 * FPS)))
    # 养成系统面板（v2.2.1）
    # style 每游戏固定一种（游戏语义，人工确认后写入 config，不得中途改判）：
    #   gray2color = 灰色锁定→彩色点亮（同副本面板的解锁方式与阈值）
    #   firstfill  = 空剪影→首次填入（首填语义，阈值较严、换装/升级不记）
    cult = cfg["rois"].get("cultivation")
    if cult and cult.get("slots"):
        style = cult.get("style", "gray2color")
        for it in cult["slots"]:
            if style == "firstfill":
                tracks[it["id"]] = dict(box=it["roi"], kind="cultf",
                                        thH=16, thS=30,
                                        persist=max(2, round(1.5 * FPS)))
            else:
                tracks[it["id"]] = dict(box=it["roi"], kind="cultg",
                                        thH=13, thS=18,
                                        persist=max(2, round(1.5 * FPS)))
    return cfg, tracks

# ---------- 工具 ----------
def dhash(img, size=8):
    g = cv2.cvtColor(cv2.resize(img, (size+1, size)), cv2.COLOR_BGR2GRAY)
    return g[:, 1:] > g[:, :-1]

ham = lambda a, b: int(np.count_nonzero(a != b))

def sat_val(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return float(hsv[:, :, 1].mean()), float(hsv[:, :, 2].mean())

fmtt = lambda t: f"{int(t)//60:02d}:{int(t)%60:02d}"


def _drop_ev(path):
    """撤销携带候选时清掉预写的证据图"""
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def identity_pass(events, fdir, files, cfg):
    """v2.3 礼包面板图标身份核验（想法2：认图标不认格子）
    名册制：每个格子报警时，把"稳定后的画面"(连下方文字标签)与已登记图标比对——
      新面孔 -> identity=new，保留为登场事件并登记入名册
      老面孔回到原格 -> identity=repeat（重现/弹跳，剔除）
      老面孔出现在别的格 -> identity=moved（槽位移位，剔除；登场早已记过）
      内容一闪而过站不稳 -> identity=transient（漫游NPC/气泡/飘字，剔除）
    人只负责给新面孔命名（names.json），机器不猜图标身份。"""
    boxes = {b["id"]: b["roi"] for b in cfg["rois"]["activity"]}
    faces = []   # 名册：{h: 稳定帧指纹, box: 首次登场格, t_disp}

    def crop_at(bid, i):
        x, y, w, h = boxes[bid]
        im = imread_u(os.path.join(fdir, files[min(i, len(files)-1)]))
        return im[y:y+h+12, x:x+w]     # 向下多裁12px：含图标文字标签

    for e in sorted((e for e in events if e["kind"] == "band"), key=lambda e: e["t"]):
        if e.get("init_transient"):
            continue                    # 开局瞬态不参与名册，避免登记空板/特效
        bid = e["id"][4:] if e["id"].startswith("ACT_") else e["id"]
        if bid not in boxes:
            continue
        i0 = max(0, int(e["t"] * FPS))
        settled = None
        for j in range(i0, min(i0 + 13, len(files) - 2)):
            if ham(dhash(crop_at(bid, j)), dhash(crop_at(bid, j + 2))) <= 8:
                settled = crop_at(bid, j + 2)   # 1秒内画面站稳=真实登场/移位
                break
        if settled is None:
            e["identity"] = "transient"
            continue
        hs = dhash(settled)
        hit = next((f for f in faces if ham(hs, f["h"]) <= 11), None)
        if hit is None:
            faces.append(dict(h=hs, box=bid, t_disp=e["t_disp"]))
            e["identity"] = "new"
        elif hit["box"] == bid:
            e["identity"] = "repeat"
        else:
            e["identity"] = "moved"
            e["moved_face_from"] = hit["box"]
    return events

def extract_frames(video, wdir, fps):
    fd = os.path.join(wdir, "frames")
    os.makedirs(fd, exist_ok=True)
    have = len([f for f in os.listdir(fd) if f.endswith(".png")])
    durp = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                           "-of","csv=p=0",video], capture_output=True, text=True)
    try: need = int(float(durp.stdout.strip()) * fps) + 1
    except Exception: need = -1
    if have < need:
        subprocess.run(["ffmpeg","-v","error","-i",video,"-vf",f"fps={fps}",
                        "-q:v","2","-start_number","0",
                        os.path.join(fd,"f_%05d.png")], check=True)
    return fd, sorted(f for f in os.listdir(fd) if f.endswith(".png"))

def classify_refs(frames_dir, files, anchors, n_auto=6, gate=None):
    """主页面基准帧：优先用人工给的锚点；否则自动取整片均匀样本聚类最大簇
    gate=(x,y,w,h) 时只在稳定子区域上算哈希（主页带动画的游戏必需）"""
    def _crop(im):
        if gate:
            gx, gy, gw, gh = gate
            return im[gy:gy+gh, gx:gx+gw]
        return im
    N = len(files)
    idxs = []
    for grp in ("main", "battle", "popup"):
        for t in anchors.get(grp, []):
            p = [int(x) for x in t.split(":")]
            sec = p[-1] + p[-2]*60 + (p[-3]*3600 if len(p) > 2 else 0)
            i = min(N-1, int(sec) * FPS)
            if grp == "main": idxs.append(i)
    if not idxs:                              # 自动：均匀抽样当main候选
        step = max(1, N // (n_auto * FPS))
        idxs = list(range(0, N, step))
    hs, vs = [], []
    for i in idxs:
        im = imread_u(os.path.join(frames_dir, files[i]))
        hs.append(dhash(_crop(im)))
        vs.append(float(cv2.cvtColor(_crop(im), cv2.COLOR_BGR2HSV)[:, :, 2].mean()))
    # 最大簇：两两距离<15 的最大一致组
    best = []
    for h in hs:
        grp = [x for x in hs if ham(x, h) < 15]
        if len(grp) > len(best): best = grp
    if not best: best = hs[:1]
    med = best[0]
    mainH = [h for h in hs if ham(h, med) < 18] or [med]
    mainV = float(np.mean(vs))                # 主页面亮度参照（供压暗判定）
    return mainH, mainV

def sessions(arr, cid, min_len=4):
    out, st = [], None
    for i, v in enumerate(arr):
        if v == cid and st is None: st = i
        elif v != cid and st is not None:
            if i - st >= min_len: out.append((st, i-1))
            st = None
    if st is not None: out.append((st, len(arr)-1))
    return out

def main():
    global FPS
    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    video, gdir = pos[0], pos[1]
    if "--fps" in sys.argv:                    # 强制细扫：--fps 30
        FPS = max(1, int(sys.argv[sys.argv.index("--fps") + 1]))
    cfg, tracks = load_cfg(gdir)
    anchors = cfg.get("anchors", {})
    gate = cfg.get("gate_roi")                # 场景门控子区域（主页有动画的游戏用）
    # 工作目录按帧率隔离，粗/细扫产物互不覆盖
    wdir = os.path.join(gdir, "work") if FPS == 2 else os.path.join(gdir, f"work_f{FPS}")
    os.makedirs(wdir, exist_ok=True)
    evd = os.path.join(wdir, "ev"); os.makedirs(evd, exist_ok=True)
    print(f"[mode] fps={FPS}")

    fdir, files = extract_frames(video, wdir, FPS)
    N = len(files)
    print(f"[frames] {N}")

    refs, Vref = classify_refs(fdir, files, anchors, gate=gate)
    dim_ratio = float(cfg.get("params", {}).get("dim_ratio", 0.85))
    # v2.3 开关：弱信号跨遮挡携带 / 礼包面板图标身份核验（默认关，config params 开启）
    carry = bool(cfg.get("params", {}).get("carry_candidate"))
    identity = bool(cfg.get("params", {}).get("identity_check"))
    # v2.5 开关：短遮挡重见 nav 强制对比（默认关，config params 开启，见手册9.8）
    short_on = bool(cfg.get("params", {}).get("short_gap_force"))
    cls_arr = np.zeros(N, dtype=np.int8)      # 0 unknown 1 main 2 other
    state, events = {}, []
    prev_main_i = None                        # 上一次主页可视帧（遮挡起点基准）

    for i, fn in enumerate(files):
        img = imread_u(os.path.join(fdir, fn))
        if img is None: continue
        gimg = img
        if gate:
            gx, gy, gw, gh = gate
            gimg = img[gy:gy+gh, gx:gx+gw]
        hf = dhash(gimg)
        dmin = min(ham(hf, r) for r in refs)
        is_main = dmin < 22
        if is_main:                           # 压暗保护：亮度骤降的主页帧视作遮挡
            Vnow = float(cv2.cvtColor(gimg, cv2.COLOR_BGR2HSV)[:, :, 2].mean())
            if Vref and Vnow < dim_ratio * Vref:
                is_main = False
            else:
                Vref = 0.95 * Vref + 0.05 * Vnow   # 稳态缓更新
        cls_arr[i] = 1 if is_main else 2
        if cls_arr[i] != 1:
            continue
        t = i / FPS
        # --- 主页重见强制对比：跨遮挡恢复可见时，先与起点基线一次性对比 ---
        gap_frames = (i - prev_main_i - 1) if prev_main_i is not None else 0
        force = gap_frames >= 3 * FPS
        sgap = short_on and 1 <= gap_frames < 3 * FPS   # 短遮挡：长遮挡通道以下的全部间隙
        for rid, tr in tracks.items():
            st = state.setdefault(rid, dict(base=None, baseS=None, init_i=None,
                                            cH=None, cS=None, ci=None,
                                            sH=None, sS=None, si=None,
                                            sconf=0, base_i=None))
            x, y, w, h = tr["box"]
            if x+w > img.shape[1] or y+h > img.shape[0]:
                continue                        # 越界保护
            crop = img[y:y+h, x:x+w]
            hh = dhash(crop); S, _V = sat_val(crop)
            if st["base"] is None:
                st.update(base=hh, baseS=S, init_i=i, base_i=i); continue
            dh0 = ham(hh, st["base"]); dsat0 = S - st["baseS"]
            if force and (dh0 >= tr["thH"] or abs(dsat0) >= tr["thS"]):
                # 用户规则：遮挡期间发生的变化，以"重见后第一帧"为解锁时刻
                tag = f"{rid}_f{i:05d}"
                rec = dict(id=rid, kind=tr["kind"], t=round(t, 1),
                           t_disp=fmtt(t), mode="reveal",
                           gap_start=fmtt(prev_main_i/FPS),
                           ham=dh0, dsat=round(dsat0, 1), name="",
                           fill_like=(tr["kind"] == "cultf" and dsat0 >= 20))
                bimg = imread_u(os.path.join(fdir,
                                  files[prev_main_i]))[y:y+h, x:x+w]
                sc = max(1, min(4, 320//max(w, h)))
                imwrite_u(os.path.join(evd, f"{tag}_b.png"),
                            cv2.resize(bimg, (w*sc, h*sc),
                                       interpolation=cv2.INTER_NEAREST))
                imwrite_u(os.path.join(evd, f"{tag}_a.png"),
                            cv2.resize(crop, (w*sc, h*sc),
                                       interpolation=cv2.INTER_NEAREST))
                rec["ev"] = f"ev/{tag}"
                events.append(rec)
                st.update(base=hh, baseS=S, base_i=i, cH=None, cS=None, ci=None,
                          sH=None, sS=None, si=None)
            elif force:
                # v2.3 弱信号携带：遮挡前出现过、自身站稳过(≥2主页帧)的"待定样子"，
                # 若重见帧与它一致且明显更接近它而非旧基线，先挂起(pend)，
                # 由后续主页帧连续确认后才入账，时刻记候选首现帧
                done = False
                if carry and st["sH"] is not None and st.get("sconf", 0) >= 1:
                    d_cand = ham(hh, st["sH"])
                    d_base = ham(hh, st["base"])
                    if d_cand <= 8 and d_cand < d_base and d_base >= 9:
                        tag = f"{rid}_f{i:05d}"
                        bimg = imread_u(os.path.join(fdir,
                                        files[st["base_i"]]))[y:y+h, x:x+w]
                        sc = max(1, min(4, 320//max(w, h)))
                        imwrite_u(os.path.join(evd, f"{tag}_b.png"),
                                  cv2.resize(bimg, (w*sc, h*sc),
                                             interpolation=cv2.INTER_NEAREST))
                        imwrite_u(os.path.join(evd, f"{tag}_a.png"),
                                  cv2.resize(crop, (w*sc, h*sc),
                                             interpolation=cv2.INTER_NEAREST))
                        st["pend"] = dict(si=st["si"], tag=tag,
                                          cH=st["sH"],
                                          obase=st["base"], obaseS=st["baseS"],
                                          ham=d_base, dsat=round(dsat0, 1),
                                          gap=fmtt(prev_main_i/FPS),
                                          conf=0, amb=0)
                        st.update(base=hh, baseS=S, base_i=i, cH=None, cS=None,
                                  ci=None, sH=None, sS=None, si=None, sconf=0)
                        done = True
                if not done:
                    st.update(cH=None, cS=None, ci=None,
                              sH=None, sS=None, si=None, sconf=0)   # 重见无变化：清残留候选
            elif sgap and tr["kind"] == "nav" and st.get("pend") is None \
                    and (dh0 >= tr["thH"] or abs(dsat0) >= tr["thS"]):
                # v2.5 短遮挡强制对比：重见帧幅度超阈值立即入账，不等persist——
                # persist会被"解锁即点击进入"的动画逐帧重置（灵画师挑战11:42案例）
                tag = f"{rid}_f{i:05d}"
                rec = dict(id=rid, kind=tr["kind"], t=round(t, 1),
                           t_disp=fmtt(t), mode="direct", short_gap=1,
                           ham=dh0, dsat=round(dsat0, 1), name="",
                           fill_like=False)
                bimg = imread_u(os.path.join(fdir,
                                  files[prev_main_i]))[y:y+h, x:x+w]
                sc = max(1, min(4, 320 // max(w, h)))
                imwrite_u(os.path.join(evd, f"{tag}_b.png"),
                          cv2.resize(bimg, (w * sc, h * sc),
                                     interpolation=cv2.INTER_NEAREST))
                imwrite_u(os.path.join(evd, f"{tag}_a.png"),
                          cv2.resize(crop, (w * sc, h * sc),
                                     interpolation=cv2.INTER_NEAREST))
                rec["ev"] = f"ev/{tag}"
                events.append(rec)
                st.update(base=hh, baseS=S, base_i=i, cH=None, cS=None, ci=None,
                          sH=None, sS=None, si=None, sconf=0, pend=None)
        if force:
            prev_main_i = i
            continue                       # 本帧强制通道已处理，跳过常规追踪
        for rid, tr in tracks.items():
            st = state.setdefault(rid, dict(base=None, baseS=None, init_i=None,
                                            cH=None, cS=None, ci=None,
                                            sH=None, sS=None, si=None,
                                            sconf=0, base_i=None))
            x, y, w, h = tr["box"]
            if x+w > img.shape[1] or y+h > img.shape[0]:
                continue                        # 越界保护
            crop = img[y:y+h, x:x+w]
            hh = dhash(crop); S, _V = sat_val(crop)
            if st["base"] is None:
                st.update(base=hh, baseS=S, init_i=i, base_i=i); continue
            if st.get("pend") is not None:
                # v2.3 携带挂起确认：连续 persist 个主页帧仍是新态 -> 入账；
                # 回到旧态 -> 撤销并还原基线；两者都不是 -> 宽限计数，超限撤销
                p = st["pend"]
                if ham(hh, st["base"]) < 8 or ham(hh, p["cH"]) < 8:
                    p["conf"] += 1
                    if p["conf"] >= tr["persist"]:
                        rec = dict(id=rid, kind=tr["kind"],
                                   t=round(p["si"]/FPS, 1),
                                   t_disp=fmtt(p["si"]/FPS), mode="direct",
                                   carry=1, gap_start=p["gap"],
                                   ham=p["ham"], dsat=p["dsat"], name="",
                                   fill_like=(tr["kind"] == "cultf"
                                              and p["dsat"] >= 20))
                        rec["ev"] = f"ev/{p['tag']}"
                        events.append(rec)
                        st["pend"] = None
                elif ham(hh, p["obase"]) < 8:
                    st.update(base=p["obase"], baseS=p["obaseS"], base_i=i)
                    _drop_ev(os.path.join(evd, p["tag"] + "_b.png"))
                    _drop_ev(os.path.join(evd, p["tag"] + "_a.png"))
                    st["pend"] = None
                else:
                    p["amb"] += 1
                    if p["amb"] > 6:
                        st.update(base=p["obase"], baseS=p["obaseS"], base_i=i)
                        _drop_ev(os.path.join(evd, p["tag"] + "_b.png"))
                        _drop_ev(os.path.join(evd, p["tag"] + "_a.png"))
                        st["pend"] = None
                continue
            dh = ham(hh, st["base"]); dsat = S - st["baseS"]
            if dh >= tr["thH"] or abs(dsat) >= tr["thS"]:
                if st["ci"] is None or (ham(hh, st["cH"]) > 10 and abs(S-st["cS"]) >= tr["thS"]*0.6):
                    st.update(cH=hh, cS=S, ci=i)
                elif i - st["ci"] >= tr["persist"]:
                    j = st["ci"] - 1
                    while j >= 0 and cls_arr[j] != 1: j -= 1
                    tag = f"{rid}_f{i:05d}"
                    # 用户规则：跨越遮挡的变化 -> 记录"遮挡结束后一帧"为时刻，
                    # 并保留遮挡区间[t_before, t]；前后一致则本就不触发事件。
                    across = j >= 0 and (st["ci"] - j) >= 3 * FPS
                    rec = dict(id=rid, kind=tr["kind"],
                               t=round(st["ci"]/FPS, 1),
                               t_disp=fmtt(st["ci"]/FPS),
                               mode="reveal" if across else "direct",
                               gap_start=fmtt(j/FPS) if (across and j >= 0) else "",
                               init_transient=((st["init_i"] is not None) and (st["ci"]-st["init_i"]) < 8*FPS),
                               ham=dh, dsat=round(dsat, 1), name="",
                               fill_like=(tr["kind"] == "cultf" and dsat >= 20))
                    if j >= 0:
                        bimg = imread_u(os.path.join(fdir, files[j]))[y:y+h, x:x+w]
                        aimg = img[y:y+h, x:x+w]
                        sc = max(1, min(4, 320//max(w, h)))
                        for src, suf in ((bimg, "b"), (aimg, "a")):
                            imwrite_u(os.path.join(evd, f"{tag}_{suf}.png"),
                                        cv2.resize(src, (w*sc, h*sc),
                                                   interpolation=cv2.INTER_NEAREST))
                        rec["ev"] = f"ev/{tag}"
                    events.append(rec)
                    st.update(base=st["cH"], baseS=st["cS"], base_i=i,
                              cH=None, cS=None, ci=None, sH=None, sS=None, si=None)
            else:
                if st["ci"] is not None and ham(hh, st["base"]) < 8:
                    st.update(cH=None, cS=None, ci=None)
                # v2.3 软候选：幅度未过报警线的变化也登记"待定样子"，
                # 须在后续主页帧站稳(≥2帧，sconf≥1)才有资格被跨遮挡携带确认
                if carry and (dh >= 6 or abs(dsat) >= 8):
                    if st["sH"] is None or ham(hh, st["sH"]) > 6:
                        st.update(sH=hh, sS=S, si=i, sconf=0)
                    else:
                        st["sconf"] += 1   # 同一待定态延续，站稳+1
        if cls_arr[i] == 1:
            prev_main_i = i

    bat = [[fmtt(a/FPS), fmtt(b/FPS)] for a, b in sessions(cls_arr, 2)]
    pop = [[fmtt(a/FPS), fmtt(b/FPS)] for a, b in sessions(cls_arr, 0)]
    events.sort(key=lambda e: e["t"])

    # --- 自动加密复扫：重见类事件 -> 30fps 双参照精化时刻 ---
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from densify import densify2
    except Exception:
        densify2 = None
    def _parse(t):  # mm:ss -> 秒
        p = [int(x) for x in t.split(":")]
        return p[-1] + p[-2]*60 + (p[-3]*3600 if len(p) > 2 else 0)
    refined = 0
    if densify2 is not None:
        for e in events:
            if e["mode"] != "reveal" or not e.get("ev") or e.get("t_precise"):
                continue
            span = e["t"] - _parse(e.get("gap_start", e["t_disp"]))
            # 仅短遮挡做窗口内精化；长遮挡(战斗等)按规则取重见帧本身
            if not (0 < span <= 12):
                continue
            rb = imread_u(os.path.join(evd, os.path.basename(e["ev"]) + "_b.png"))
            ra = imread_u(os.path.join(evd, os.path.basename(e["ev"]) + "_a.png"))
            if rb is None or ra is None:
                continue
            try:
                r = densify2(video, tuple(tracks[e["id"]]["box"]),
                             max(0.0, _parse(e["gap_start"])), min(N/FPS, e["t"]+0.5),
                             rb, ra)
                if r:
                    m_, s_ = divmod(r["t"], 60)
                    e["t_precise"] = f"{int(m_):02d}:{s_:05.2f}"
                    refined += 1
            except Exception:
                pass
    print("[precise] refined:", refined)

    # --- v2.3 礼包面板图标身份核验：新面孔登场 / 移位·重现·瞬态剔除 ---
    if identity:
        identity_pass(events, fdir, files, cfg)
        from collections import Counter as _C
        print("[identity]", dict(_C(e.get("identity", "-") for e in events
                                    if e["kind"] == "band")))

    json.dump(dict(video=os.path.basename(video), frames=N, fps=FPS,
                   events=events, battle_sessions=bat, popup_sessions=pop),
              open(os.path.join(wdir, "timeline.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # --- MD骨架（养成槽一槽一行：只列首事件，后续变化折叠计数） ---
    cult_first, cult_extra = {}, {}
    for e in events:
        if e["kind"] == "cultf":
            if e["id"] not in cult_first:
                cult_first[e["id"]] = e
            else:
                cult_extra[e["id"]] = cult_extra.get(e["id"], 0) + 1

    lines = [f"# {cfg['game']} · 解锁时间线（骨架，名称待终审）\n",
             f"- 视频：{os.path.basename(video)}，抽帧 {FPS}fps 共 {N} 帧\n"]

    if cult_first or any(e["kind"] == "cultg" for e in events):
        lines += ["## 养成系统面板（每槽一条，换装/升级不记）\n",
                  "| 槽位 | 名称(待审) | 首次填入 | 精确值(30fps) | 方式 | 后续变化(不记) |",
                  "|---|---|---:|---|---|---|"]
        for rid, e in sorted(cult_first.items()):
            way = (f"遮挡后首次可见({e['gap_start']}~)" if e["mode"] == "reveal"
                   else "直接目击")
            lines.append(f"| {rid} | {e['name'] or '—'} | {e['t_disp']} | "
                         f"{e.get('t_precise','—')} | {way} | +{cult_extra.get(rid,0)} |")

    lines += ["\n## 其他事件（礼包面板 / 副本面板图标）\n",
              "| 时间 | 精确值(30fps) | 方式 | 区域ID | 名称(待审) | 幅度 | 证据 |",
              "|---:|---|---|---|---|---|---|"]
    for e in events:
        if e["kind"] == "cultf":
            continue
        ev_s = f"![]({e['ev']}_a.png)" if "ev" in e else "—"
        way = (f"遮挡后首次可见(区间{e['gap_start']}~{e['t_disp']})"
               if e["mode"] == "reveal" else "直接目击")
        tm = e.get("t_precise") or e["t_disp"]
        lines.append(f"| {tm} | {e.get('t_precise','—')} | {way} | {e['id']} | "
                     f"{e['name'] or '—'} | ham={e['ham']} dS={e['dsat']:+} | {ev_s} |")
    lines += ["\n## 战斗时段(HUD隐藏)\n"] + [f"- {a} ~ {b}" for a, b in bat]
    lines += ["\n## 可疑弹窗时段(unknown)\n"] + [f"- {a} ~ {b}" for a, b in pop]
    open(os.path.join(wdir, "report_skeleton.md"), "w", encoding="utf-8").write("\n".join(lines))
    from collections import Counter
    print("[events]", len(events), dict(Counter(e['id'] for e in events)))

if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""局部加密复扫：对嫌疑窗口内的ROI做30fps全帧率复查，输出精确入列时刻
用法示例：
  python densify.py <视频> <x> <y> <w> <h> <起秒> <止秒>
原理：只对该ROI区域裁剪抽取30fps帧 -> 以窗口首帧为"空/旧状态"基线，
     找第一个"偏离基线且保持到底"的帧 -> 其时间即精确时刻。
"""
import cv2, numpy as np, os, sys, subprocess, tempfile

def dhash(img, size=8):
    g = cv2.cvtColor(cv2.resize(img, (size+1, size)), cv2.COLOR_BGR2GRAY)
    return g[:, 1:] > g[:, :-1]

ham = lambda a, b: int(np.count_nonzero(a != b))

def sv(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return float(hsv[:, :, 1].mean()), float(hsv[:, :, 2].mean())

def densify2(video, box, t_lo, t_hi, ref_before_img, ref_after_img, fps=30,
             brightness_gate=False):
    """双参照版：区分'压暗'与'真入列'。返回第一个稳定偏向after状态的时刻
    brightness_gate=True 时额外要求帧亮度接近参照水平（严格模式）"""
    x, y, w, h = box
    tmpd = tempfile.mkdtemp(prefix="dens2_")
    subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t_lo:.2f}", "-to", f"{t_hi:.2f}",
                    "-i", video, "-vf", f"crop={w}:{h}:{x}:{y},fps={fps}",
                    "-start_number", "0",
                    os.path.join(tmpd, "d_%05d.png")], check=True)
    files = sorted(f for f in os.listdir(tmpd) if f.endswith(".png"))
    hb = dhash(ref_before_img); ha = dhash(ref_after_img)
    bS, bV = sv(ref_before_img); aS, aV = sv(ref_after_img)
    v_ok = max(bV, aV) * 0.85

    def side(im):
        hh = dhash(im); S, V = sv(im)
        if brightness_gate and (im is None or V < v_ok):
            return "?"
        db = min(90, ham(hh, hb) * 2 + abs(S-bS) // 2)
        da = min(90, ham(hh, ha) * 2 + abs(S-aS) // 2)
        return "A" if da < db else ("B" if db < da else "?")

    labels = []
    for fn in files:
        im = cv2.imread(os.path.join(tmpd, fn))
        labels.append(side(im) if im is not None else "?")
    need = int(fps * 0.4)                     # 稳定0.4秒才认
    run = 0
    for i, lb in enumerate(labels):
        run = run + 1 if lb == "A" else 0
        if run == need:
            # t = 停稳时刻(连续need帧的起点)；t_first = 最终A段里最后一个B之后的
            # 第一帧 ≈ "开始出现"时刻（带入场动画的图标应报 t_first 而非 t）。
            # 若窗口起点即A(找不到B)，说明窗口设晚/参照错，t_first 置 None 提示重设。
            rs = i - need + 1
            k = rs
            while k >= 0 and labels[k] != "B":
                k -= 1
            t_first = (t_lo + (k + 1)/fps) if k >= 0 else None
            return dict(t=t_lo + rs/fps, t_first=t_first,
                        checked=len(files),
                        seq="".join("1" if x == "A" else x if x != "?" else "." for x in labels))
    return None

if __name__ == "__main__":
    # CLI：参照图取窗口两端画面（视作 旧状态/新状态），适合人工快速精化单个窗口
    # 用法：python densify.py <视频> <x> <y> <w> <h> <起秒> <止秒>
    import tempfile
    v = sys.argv[1]
    box = tuple(int(k) for k in sys.argv[2:6])
    lo, hi = float(sys.argv[6]), float(sys.argv[7])
    x, y, w, h = box
    tmpd = tempfile.mkdtemp(prefix="dens_cli_")
    for tag, t in (("b", lo), ("a", max(lo + 0.04, hi - 0.04))):
        subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", v,
                        "-frames:v", "1", "-vf", f"crop={w}:{h}:{x}:{y}",
                        os.path.join(tmpd, f"ref_{tag}.png")], check=True)
    rb = cv2.imread(os.path.join(tmpd, "ref_b.png"))
    ra = cv2.imread(os.path.join(tmpd, "ref_a.png"))
    assert rb is not None and ra is not None, "参照帧抽取失败（窗口越界或视频打不开）"
    r = densify2(v, box, lo, hi, rb, ra)
    if r:
        m1, s1 = divmod(r["t"], 60)
        line = f"precise_time(停稳) = {int(m1):02d}:{s1:05.2f}"
        if r.get("t_first"):
            m2, s2 = divmod(r["t_first"], 60)
            line += f"   t_first(出现) = {int(m2):02d}:{s2:05.2f}"
        print(line, f"  [checked {r['checked']} frames]")
    else:
        print("no sustained change found in window")

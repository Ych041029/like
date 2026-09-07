# -*- coding: utf-8 -*-
"""通用解锁时间线工具 · 第一步：人工标定（A引导+B复核 组合）

用法：
  python calibrate.py <视频文件> [mm:ss]     # mm:ss 选抽帧时刻，默认自动取中段
流程（A：按类别引导，乱序无关）：
  1) 弹窗显示抽出的帧
  2) 依次提示三个类别：【礼包面板】→【副本面板】→【养成系统面板】
     - 每类可画多个框（每拖一框按 ENTER 确认）
     - 该类不想框就按 ESC 跳过；三类全走完自动结束
  3) 自动生成：games/<游戏名>/config.json + crop_*.png 预览图
B部分：把预览图发给 AI 复核类别与名称，或直接改 config.json。
"""
import cv2, os, sys, json, subprocess
import numpy as np

def imread_u(path):
    """cv2.imread 在 Windows 上读不了含中文/非ASCII的路径，用 imdecode 兜底"""
    try:
        return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return cv2.imread(path)

def get_frame(video, ts=None):
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_calib_frame.png")
    if not ts:
        dur = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                              "-of","csv=p=0", video], capture_output=True, text=True)
        try: t = float(dur.stdout.strip()) * 0.5
        except Exception: t = 60
    else:
        m,s = ts.split(":"); t = int(m)*60+int(s)
    subprocess.run(["ffmpeg","-v","error","-ss",f"{int(t//60):02d}:{int(t%60):02d}",
                    "-i",video,"-frames:v","1","-y",out], check=True)
    return out, f"{int(t//60):02d}:{int(t%60):02d}"

CATS = [   # (key, 中文提示, 窗口提示英文)
    ("activity", "礼包面板",     "GIFT PANEL: drag -> ENTER; ESC=next category"),
    ("nav",      "副本面板",     "NAV PANEL: one box per icon; ENTER confirm; ESC=next"),
    ("cultivation", "养成系统面板", "CULTIVATION: one box per slot; ENTER confirm; ESC=next"),
]

def main():
    a = sys.argv[1:]
    IMG_EXT = (".png", ".jpg", ".jpeg", ".bmp")
    img_given = bool(a) and a[0].lower().endswith(IMG_EXT)
    if img_given:
        # 方式一（推荐）：人工在播放器里暂停截图，直接把干净帧图片拖进来
        # 用法：python calibrate.py 干净帧.png [视频路径（用于分辨率校准，可选）]
        frame_path = a[0]
        video = a[1] if len(a) > 1 else frame_path
        img = imread_u(frame_path)
        assert img is not None, "读取截图失败: " + frame_path
        tstr = "manual"
        H, W = img.shape[:2]
        if len(a) > 1:
            # cv2.VideoCapture 同样读不了中文路径，改用 ffprobe 取分辨率
            r = subprocess.run(["ffprobe","-v","error","-select_streams","v:0",
                                "-show_entries","stream=width,height",
                                "-of","csv=s=x:p=0", a[1]], capture_output=True, text=True)
            try: Wv, Hv = [int(x) for x in r.stdout.strip().split("x")]
            except Exception: Wv = Hv = 0
            if Wv and (W, H) != (Wv, Hv):
                img = cv2.resize(img, (Wv, Hv))
                print(f"[warn] 截图 {W}x{H} 与视频 {Wv}x{Hv} 不一致，已缩放到视频尺寸")
    else:
        # 方式二：给视频+时间点，由工具抽帧
        video = a[0]
        ts = a[1] if len(a) > 1 else None
        frame_path, tstr = get_frame(video, ts)
        img = cv2.imread(frame_path)
    H, W = img.shape[:2]
    print(f"[frame] {tstr} from {os.path.basename(video)} ({W}x{H})")

    banner = img.copy()
    cv2.rectangle(banner,(0,0),(W,40),(30,30,30),-1)
    show = banner.copy()
    rois = {"activity": [], "nav": [], "cultivation": []}

    cv2.namedWindow("CALIBRATE-A", cv2.WINDOW_AUTOSIZE)
    for key, zh, en in CATS:
        hint = img.copy()
        cv2.rectangle(hint,(0,0),(W,46),(30,30,30),-1)
        cv2.putText(hint, en, (8,20), cv2.FONT_HERSHEY_SIMPLEX,0.5,(0,255,255),1)
        cv2.putText(hint, f"category: {key}   (drag->ENTER xN, ESC=skip/next)",
                    (8,38), cv2.FONT_HERSHEY_SIMPLEX,0.45,(255,255,255),1)
        colors = [(0,0,255),(0,255,255),(0,255,0),(255,0,255)]
        ci = 0
        while True:
            r = cv2.selectROI("CALIBRATE-A", hint if not rois[key]
                              else _with_marks(hint, rois), True, False)
            if r == (0,0,0,0):
                break
            if r[2] > 5 and r[3] > 5:
                rois[key].append([int(v) for v in r])
                x,y,w,h = [int(v) for v in r]
                cv2.rectangle(hint,(x,y),(x+w,y+h),colors[ci%4],2)
                cv2.putText(hint,f"{key}{len(rois[key])}",(x+3,y+16),
                            cv2.FONT_HERSHEY_SIMPLEX,0.45,colors[ci%4],2)
                ci += 1
                print(f"[{key}] box{ci}: {x},{y},{w},{h}")
    cv2.destroyAllWindows()

    game = input_ascii("game name (folder name, ascii): ")
    gdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "games", game or "default")
    os.makedirs(gdir, exist_ok=True)
    cfg = {"game": game, "calib_frame_time": tstr, "video_resolution": f"{W}x{H}",
           "rois": {"activity": [{"id": f"act{i+1}", "roi": b} for i,b in enumerate(rois["activity"])],
                    "nav":      [{"id": f"nav{i+1}", "roi": b} for i,b in enumerate(rois["nav"])],
                    "cultivation": ({"style": "", "slots": [{"id": f"cult{i+1}", "roi": b} for i,b in enumerate(rois["cultivation"])],
                                     "note": "样式(style)需人工确认后填入: gray2color=灰锁变彩色 / firstfill=空剪影首填"}
                                    if rois["cultivation"] else None)},
           "params": {}}
    json.dump(cfg, open(os.path.join(gdir,"config.json"),"w",encoding="utf-8"),
              ensure_ascii=False, indent=1)
    cv2.imwrite(os.path.join(gdir, "calib_frame.png"), img)   # 留档标定基准帧
    n_boxes = len(rois["activity"]) + len(rois["nav"]) + len(rois["cultivation"])
    # 每个框裁剪预览
    idx = 0
    for cat in ("activity","nav","cultivation"):
        for item in cfg["rois"][cat]:
            idx += 1
            x,y,w,h = item["roi"]
            sc = max(1,min(4,300//max(w,max(h,1))))
            cv2.imwrite(os.path.join(gdir,f"crop_{item['id']}.png"),
                        cv2.resize(img[y:y+h,x:x+w],(w*sc,h*sc),
                                   interpolation=cv2.INTER_NEAREST))
    print(f"[done] {n_boxes} boxes -> {gdir}\\config.json")
    print("[next] 把各 crop_*.png 发给AI复核命名")
    if rois["cultivation"]:
        print("[next] 养成系统面板样式需人工确认后填入 config 的 cultivation.style：")
        print("       gray2color=灰锁变彩色(同副本面板) / firstfill=空剪影首填")

def _with_marks(base, rois):
    m = base.copy()
    for cat in ("activity","nav","cultivation"):
        for item in rois[cat]:
            b = item if isinstance(item,list) else item.get("roi")
            if isinstance(b, list) and len(b)==4:
                x,y,w,h = b
                cv2.rectangle(m,(x,y),(x+w,y+h),(0,200,255),2)
    return m

def input_ascii(prompt):
    try: return input(prompt).strip()
    except Exception: return "default"

if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
游戏游玩视频分析器（神器传说 专用版，可通用）
==============================================
输入一段游戏游玩视频，按【一秒两帧】（2 fps）抽取画面照片，分析后输出 Markdown 文档：
  1. 游戏概述（总体玩法）
  2. 核心循环（该游戏的玩法循环）

工作方式：
  - 抽帧：严格 2 fps（每秒 2 张照片），用 ffmpeg 抽到 frames/ 目录。
  - 分析：对抽出的帧做【时间均匀下采样】得到一组代表性帧（默认 90 张），逐帧 PaddleOCR
         提取文字；再按规则 + 可选视觉大模型综合分析。这样既满足"一秒两帧"的抽帧要求，
         又避免对数千帧全量 OCR 造成的超长耗时。
  - 输出：Markdown 文档，存到 D:\\ych\\no.1\\。

使用方式
--------
  python game_analyzer.py                         # 用下面 VIDEO 默认路径
  python game_analyzer.py "D:\\xxx.mp4"           # 指定视频
  python game_analyzer.py "D:\\xxx.mp4" 150       # 指定分析采样帧数
  python game_analyzer.py "D:\\xxx.mp4" --out "D:\\报告目录"   # ★ 自定义输出路径
  python game_analyzer.py "D:\\xxx.mp4" 90 --out "D:\\报告目录"  # 同时指定帧数和输出路径
  python game_analyzer.py "D:\\xxx.mp4" --reuse-frames "D:\\已有帧目录"  # ★ 复用已抽好的帧(跳过抽帧,配合 run_all.py 共用抽帧)

可选：接入视觉大模型做深度理解（强烈推荐，能让概述/循环写得更准）：
  set GAME_LLM_API_KEY=sk-xxxx
  set GAME_LLM_BASE_URL=https://api.openai.com/v1   (可选，默认 OpenAI 官方)
  set GAME_LLM_MODEL=gpt-4o                          (可选)

输出路径（默认 D:\\ych\\no.1）：
  - 不传 --out：结果输出到脚本顶部 OUT_DIR（默认 D:\\ych\\no.1）。
  - 传 --out "路径"：结果输出到你指定的目录（不存在会自动创建）。

核心循环图：
  - 脚本会把核心循环画成环形流程图 PNG。
  - EMBED_IMAGE=False（默认）：md 用相对路径引用 png，需保证 png 与 md 在同一目录。
  - EMBED_IMAGE=True：图片以 base64 内嵌进 md，**单文件自包含**，
    把 md 单独拷走/发给别人也能直接看到图。
  - EMBED_IMAGE=False：md 用相对路径引用 png，需保证 png 与 md 在同一目录。

依赖（均已安装）: cv2, numpy, PIL, paddleocr, ffmpeg/ffprobe
产物: frames\\(2fps全量抽帧), report\\, game_report_<时间戳>.md
"""

import os, sys, re, json, base64, subprocess, datetime, urllib.request, math
from collections import Counter

# ============== 核心循环环形图绘制 ==============
def draw_core_loop(steps, out_png, title="核心循环"):
    """把核心循环步骤画成顺时针环形流程图，保存为 PNG。失败返回 None。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyArrowPatch, Circle
        import matplotlib.font_manager as fm
    except Exception as e:
        print(f"      [图] matplotlib 不可用，跳过画图: {e}")
        return None
    # 中文字体：优先微软雅黑 → 黑体 → 宋体
    font_path = None
    for cand in [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf",
                 r"C:\Windows\Fonts\simsun.ttc", r"C:\Windows\Fonts\Deng.ttf"]:
        if os.path.exists(cand):
            font_path = cand; break
    fp = fm.FontProperties(fname=font_path) if font_path else fm.FontProperties()
    plt.rcParams["axes.unicode_minus"] = False

    n = len(steps)
    if n == 0:
        return None
    R = 1.0
    # 节点坐标：从正上方(12点)起，顺时针均匀分布
    pts = []
    for i in range(n):
        ang = math.pi / 2 - i * (2 * math.pi / n)
        pts.append((R * math.cos(ang), R * math.sin(ang)))

    palette = ["#3b6fb6", "#4a90c2", "#5bb0a0", "#e0a458", "#d96666", "#8e6fb0",
               "#3fa7a0", "#c47bb0", "#6aa84f", "#b8860b"]
    # 单步退化（只有 1-2 步）时改用横向流程，避免环形退化为点
    if n <= 2:
        fig, ax = plt.subplots(figsize=(max(6, 2.5 * n), 3))
        ax.set_xlim(-0.5, n - 0.5); ax.set_ylim(-1, 1); ax.set_aspect('equal'); ax.axis('off')
        xs = [i for i in range(n)]
        for i, x in enumerate(xs):
            ax.add_patch(Circle((x, 0), 0.28, color=palette[i % len(palette)], zorder=3, ec='white', lw=2))
            ax.text(x, 0, str(i + 1), color='white', ha='center', va='center', fontsize=18,
                    fontweight='bold', fontproperties=fp, zorder=4)
            ax.text(x, -0.55, steps[i], ha='center', va='center', fontsize=14,
                    fontproperties=fp, color='#222', zorder=4)
            if i < n - 1:
                ax.add_patch(FancyArrowPatch((xs[i] + 0.28, 0), (xs[i + 1] - 0.28, 0),
                             arrowstyle='-|>', mutation_scale=26, color='#888', lw=2.2, zorder=2))
        plt.tight_layout()
        plt.savefig(out_png, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        return out_png

    # 环形布局
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.set_xlim(-1.7, 1.7); ax.set_ylim(-1.7, 1.7); ax.set_aspect('equal'); ax.axis('off')

    # 节点 + 标签
    for i, (x, y) in enumerate(pts):
        ax.add_patch(Circle((x, y), 0.26, color=palette[i % len(palette)], zorder=3, ec='white', lw=2))
        ax.text(x, y, str(i + 1), color='white', ha='center', va='center', fontsize=18,
                fontweight='bold', fontproperties=fp, zorder=4)
        ax.text(1.32 * x, 1.32 * y, steps[i], ha='center', va='center', fontsize=14,
                fontproperties=fp, color='#222', zorder=4)
    # 顺时针弧形箭头
    for i in range(n):
        x1, y1 = pts[i]; x2, y2 = pts[(i + 1) % n]
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), connectionstyle='arc3,rad=-0.28',
                     arrowstyle='-|>', mutation_scale=26, color='#888', lw=2.2, zorder=2))
    # 中心标题
    ax.text(0, 0.06, title, ha='center', va='center', fontsize=20, fontweight='bold',
            fontproperties=fp, color='#333')
    ax.text(0, -0.12, "CORE LOOP", ha='center', va='center', fontsize=10,
            fontproperties=fp, color='#999')

    plt.tight_layout()
    plt.savefig(out_png, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return out_png

# ============== 可调参数 ==============
VIDEO = r"D:\ych\黄策划的任务\神器传说1.mp4"   # 默认视频路径（被 sys.argv[1] 覆盖）
FPS_SAMPLE = 2                                  # ★ 抽帧频率：一秒两帧（2 fps）
ANALYZE_FRAMES = 90                             # 用于 OCR/分析的代表帧数量（从全量帧里均匀采样）
OCR_MIN_SCORE = 0.45                            # OCR 置信度过滤
LLM_MAX_IMAGES = 10                             # 发给大模型的关键帧上限
EMBED_IMAGE = False                             # ★ True=图片以base64内嵌进md(单文件自包含)；False=相对路径引用(默认,需png与md同目录)
OUT_DIR = r"D:\ych\no.1"                        # 输出根目录
# =====================================

video = sys.argv[1] if len(sys.argv) > 1 else VIDEO
if len(sys.argv) > 2:
    try:
        ANALYZE_FRAMES = int(sys.argv[2])
    except Exception:
        pass

# 输出路径：支持 --out D:\xxx 命名参数；复用抽帧：--reuse-frames "帧目录"
argv = sys.argv[1:]
out_dir = OUT_DIR
if "--out" in argv:
    i = argv.index("--out")
    if i + 1 < len(argv):
        out_dir = argv[i + 1]
OUT_DIR = out_dir

reuse_frames = None
if "--reuse-frames" in argv:
    j = argv.index("--reuse-frames")
    if j + 1 < len(argv):
        reuse_frames = argv[j + 1]

FRAMES_DIR = os.path.join(OUT_DIR, "frames")
REPORT_DIR = os.path.join(OUT_DIR, "report")
if reuse_frames:
    if not os.path.isdir(reuse_frames):
        print(f"[error] 复用帧目录不存在: {reuse_frames}")
        sys.exit(1)
else:
    os.makedirs(FRAMES_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)
SRC_FRAME_DIR = reuse_frames if reuse_frames else FRAMES_DIR   # 帧图片实际所在目录
print(f"输出目录：{OUT_DIR}" + (f"  |  复用抽帧：{reuse_frames}" if reuse_frames else ""))

# ------------------------------------------------------------------
# 阶段 1：视频探测
# ------------------------------------------------------------------
def probe(video):
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
           "-show_entries", "stream=width,height,r_frame_rate,duration",
           "-show_entries", "format=duration", "-of", "json", video]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        info = json.loads(r.stdout)
    except Exception as e:
        print(f"[warn] ffprobe 失败: {e}，使用默认参数")
        return {"duration": 1800.0, "width": 424, "height": 808, "fps": 30.0}
    st = info.get("streams", [{}])[0]
    dur = float(info.get("format", {}).get("duration") or st.get("duration") or 1800.0)
    w = int(st.get("width") or 424)
    h = int(st.get("height") or 808)
    fr = st.get("r_frame_rate", "30/1")
    try:
        a, b = fr.split("/"); fps = float(a) / float(b) if float(b) else 30.0
    except Exception:
        fps = 30.0
    return {"duration": dur, "width": w, "height": h, "fps": fps}

print(f"[1/6] 探测视频: {video}")
if not os.path.exists(video):
    print(f"[error] 视频不存在: {video}"); sys.exit(1)
info = probe(video)
DUR, W, H, FPS = info["duration"], info["width"], info["height"], info["fps"]
print(f"      时长 {DUR:.1f}s ({DUR/60:.1f}min) | {W}x{H} | 源 {FPS:.1f}fps")

# ------------------------------------------------------------------
# 阶段 2：抽帧 —— 严格一秒两帧（2 fps）；或复用已有抽帧
# ------------------------------------------------------------------
frame_index = []          # [(时间秒, 文件名, 标签)]

if reuse_frames:
    # 复用模式：直接扫描已有帧目录（支持任务2命名 X分XX秒_第N帧.jpg），跳过抽帧
    print(f"[2/6] 复用已抽好的帧（{FPS_SAMPLE} fps）...")
    pat_frame = re.compile(r'(\d+)分(\d{1,2})秒_第(\d+)帧')
    for fn in os.listdir(reuse_frames):
        m = pat_frame.match(fn)
        if m and fn.lower().endswith(".jpg"):
            t = int(m.group(1)) * 60 + int(m.group(2)) + (int(m.group(3)) - 1) / FPS_SAMPLE
            frame_index.append((t, fn, "pan"))
    frame_index.sort(key=lambda x: x[0])
    saved_files = [(t, fn) for t, fn, _ in frame_index]
    ok, fail = len(frame_index), 0
    if ok == 0:
        print(f"[error] 目录里没有可识别的帧文件（需要 X分XX秒_第N帧.jpg 命名）: {reuse_frames}")
        sys.exit(1)
    print(f"      复用帧数: {ok}（跳过抽帧）")
else:
    print(f"[2/6] 抽帧（{FPS_SAMPLE} fps = 一秒两帧）...")

    def extract_one(video, ts, out):
        cmd = ["ffmpeg", "-y", "-ss", f"{ts:.2f}", "-i", video,
               "-frames:v", "1", "-q:v", "2", out, "-loglevel", "error"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r.returncode == 0 and os.path.exists(out)

    # 时间点列表：0, 0.5, 1.0, 1.5, ... 每秒 2 个
    n_total = int(DUR * FPS_SAMPLE)
    all_times = [i / FPS_SAMPLE for i in range(n_total)]
    print(f"      计划抽取 {n_total} 帧 ...")

    ok, fail = 0, 0
    saved_files = []   # [(时间秒, 文件名)]
    # 批量抽帧：每 100 帧打印一次进度
    for i, t in enumerate(all_times):
        m = int(t // 60); s = t - m * 60
        name = f"f_{int(t):05d}_{m:02d}m{s:04.1f}s.jpg"
        out = os.path.join(FRAMES_DIR, name)
        if extract_one(video, t, out):
            ok += 1; saved_files.append((t, name))
        else:
            fail += 1
        if (i + 1) % 200 == 0:
            print(f"      进度 {i+1}/{n_total} (成功 {ok}, 失败 {fail})")

    print(f"      抽帧完成: 成功 {ok} / 失败 {fail} -> frames\\")

# ------------------------------------------------------------------
# 阶段 3：从全量帧里均匀采样代表帧，用于 OCR / 分析
# ------------------------------------------------------------------
print(f"[3/6] 采样 {ANALYZE_FRAMES} 张代表帧用于分析 ...")
saved_files.sort(key=lambda x: x[0])
if len(saved_files) > ANALYZE_FRAMES:
    step = len(saved_files) / ANALYZE_FRAMES
    sample = [saved_files[int(i * step)] for i in range(ANALYZE_FRAMES)]
else:
    sample = saved_files[:]
print(f"      实际分析 {len(sample)} 张")

# ------------------------------------------------------------------
# 阶段 4：OCR 文字提取（paddleocr）
# ------------------------------------------------------------------
print("[4/6] OCR 文字提取 ...")
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["PYTHONIOENCODING"] = "utf-8"
from PIL import Image
import numpy as np
from paddleocr import PaddleOCR

ocr = PaddleOCR(use_angle_cls=False, lang="ch", show_log=False)

ocr_results = []
for i, (t, name) in enumerate(sample):
    p = os.path.join(SRC_FRAME_DIR, name)
    try:
        im = Image.open(p).convert("RGB")
        im2 = im.resize((im.width * 2, im.height * 2))
        arr = np.asarray(im2)
        res = ocr.ocr(arr, cls=False)
        lines = []
        if res and res[0]:
            for line in res[0]:
                txt = line[1][0]; sc = line[1][1]
                if sc >= OCR_MIN_SCORE and txt.strip():
                    lines.append((txt.strip(), round(float(sc), 2)))
        ocr_results.append({"t": round(t, 1), "name": name, "texts": lines})
    except Exception as e:
        ocr_results.append({"t": round(t, 1), "name": name, "texts": [], "err": str(e)})
    if (i + 1) % 15 == 0:
        print(f"      OCR 进度 {i+1}/{len(sample)}")

with open(os.path.join(REPORT_DIR, "ocr_results.json"), "w", encoding="utf-8") as f:
    json.dump(ocr_results, f, ensure_ascii=False, indent=2)
print(f"      OCR 完成 -> report/ocr_results.json")

# ------------------------------------------------------------------
# 阶段 5a：本地基线分析
# ------------------------------------------------------------------
print("[5/6] 分析游戏概述与核心循环 ...")

all_texts = [t for r in ocr_results for t, _ in r["texts"]]

# 5.1 类型推断（数据驱动：每种类型自带关键词/动作/循环/机制）
# —— 覆盖主流游戏类型，脚本对任意游戏都能给出合理结论
GENRES = [
  {"name":"放置/挂机修仙RPG", "kws":["炼气","修炼","渡劫","境界","灵气","挂机","离线","收益","宗门","炼器","法宝","元神","丹药"],
   "view":"竖屏 / 第三人称（界面驱动）", "actions":["挂机","修炼","炼气","突破","渡劫","炼器","炼制","强化","升星","镶嵌","挑战","试炼"],
   "loop":["挂机/自动战斗","积累资源/经验","强化装备/修炼境界","挑战更高关卡","解锁新内容"],
   "mech":[("养成系统","炼气/境界/突破/渡劫等修仙养成线"),("装备/炼器系统","强化、升星、镶嵌、熔炼、神器养成"),("放置/挂机系统","自动战斗、离线收益")]},

  {"name":"ARPG/动作角色扮演", "kws":["装备","强化","技能","主线","击败","经验","属性","副本","BOSS","连招","闪避","道具","天赋"],
   "view":"第三人称", "actions":["击败","升级","强化","装备","技能","副本","BOSS","闪避","连招","任务","挑战","天赋"],
   "loop":["探索地图","战斗击败敌人","获取经验/装备","升级强化角色","挑战更强BOSS"],
   "mech":[("战斗系统","技能/连招/闪避/伤害"),("装备系统","装备获取与强化"),("成长系统","经验/等级/属性/天赋")]},

  {"name":"回合制RPG", "kws":["回合","必杀","MP","HP","队伍","施法","防御","速度","行动","奥义","普攻"," buff"],
   "view":"上帝视角", "actions":["回合","普攻","技能","必杀","防御","道具","击败","队伍","升级","施法"],
   "loop":["进入战斗","回合决策(攻/防/技)","击败敌人","获取经验/奖励","强化队伍"],
   "mech":[("回合战斗系统","回合行动/普攻/技能/必杀"),("队伍系统","角色编队与养成")]},

  {"name":"射击/FPS/TPS", "kws":["瞄准","击杀","弹药","换弹","爆头","复活","准星","护甲","手雷","得分","武器","瞄准镜"],
   "view":"第一人称", "actions":["瞄准","射击","换弹","击杀","爆头","复活","手雷","护甲"],
   "loop":["瞄准射击","击杀敌人","换弹/补给","推进/占领目标","复活重试"],
   "mech":[("射击系统","瞄准/射击/换弹/爆头"),("武器系统","武器切换/弹药管理"),("得分系统","击杀得分/排名")]},

  {"name":"MOBA/竞技", "kws":["推塔","兵线","补刀","助攻","击杀","打野","回城","对线","水晶","高地","经济"],
   "view":"俯视/斜视", "actions":["补刀","推塔","击杀","助攻","打野","对线","回城"],
   "loop":["对线发育","补刀/打野攒经济","团战击杀","推塔推进","摧毁水晶/基地"],
   "mech":[("对线系统","补刀/经济发育"),("团战系统","技能配合/击杀"),("推塔系统","兵线推进/拆塔")]},

  {"name":"生存建造/沙盒", "kws":["建造","采集","合成","制作","资源","木材","矿石","饥饿","夜晚","工作台","工具","血量"],
   "view":"第一/第三人称", "actions":["采集","建造","合成","制作","探索","生存","战斗","种植"],
   "loop":["采集资源","合成/制作工具","建造庇护所","抵御怪物(夜晚)","探索更大世界"],
   "mech":[("采集系统","砍伐/挖掘/收集资源"),("合成系统","工具/物品制作"),("建造系统","建筑/庇护所"),("生存系统","饥饿/血量/夜晚")]},

  {"name":"卡牌/策略", "kws":["抽卡","出牌","法力","随从","卡组","手牌","费用","召唤","法术","场面"],
   "view":"上帝视角", "actions":["抽卡","出牌","召唤","法术","费用","抽牌","过牌","斩杀"],
   "loop":["抽牌/积累法力","出牌召唤随从","控制场面","削减对方血量","取得胜利"],
   "mech":[("卡牌系统","抽牌/出牌/卡组构筑"),("法力系统","费用管理"),("场面系统","随从/法术")]},

  {"name":"模拟经营", "kws":["营业","收入","顾客","雇佣","利润","店铺","设施","满意度","扩建","收银"],
   "view":"俯视/上帝视角", "actions":["建造","营业","雇佣","升级","收集","经营","扩建","收银"],
   "loop":["经营获取收入","升级/扩建设施","雇佣员工","吸引更多顾客","扩大规模"],
   "mech":[("经济系统","收入/利润/金币"),("建造系统","店铺/设施建造"),("经营系统","顾客/满意度/雇佣")]},

  {"name":"格斗/对战", "kws":["连招","必杀","格挡","投技","对战","搓招","气槽","超必杀","眩晕","轻拳","重拳"],
   "view":"横版", "actions":["攻击","格挡","连招","必杀","投技","闪避","跳跃"],
   "loop":["接近对手","攻防博弈(攻/防/连招)","积攒气槽","释放必杀","击败对手"],
   "mech":[("格斗系统","连招/必杀/格挡/投技"),("气槽系统","积攒释放超必杀")]},

  {"name":"竞速/赛车", "kws":["漂移","加速","氮气","赛道","圈数","排名","计时","刹车","改装","终点","超车"],
   "view":"第三人称", "actions":["加速","漂移","刹车","氮气","超车","改装"],
   "loop":["起跑加速","漂移过弯","使用氮气","超越对手","冲过终点"],
   "mech":[("驾驶系统","加速/漂移/刹车/氮气"),("竞速系统","圈数/排名/计时"),("改装系统","车辆改装升级")]},

  {"name":"音游/节奏", "kws":["连击","判定","Perfect","Miss","音符","节奏","谱面","Combo","Full Combo","连击数"],
   "view":"固定UI", "actions":["点击","长按","滑动","连击","判定"],
   "loop":["音符出现","按节奏点击/滑动","保持连击","提升判定精度","通关谱面"],
   "mech":[("判定系统","Perfect/Good/Miss"),("连击系统","Combo/分数")]},

  {"name":"解谜/冒险", "kws":["谜题","线索","机关","解锁","密室","提示","拼图","开关","齿轮","密码","道具栏"],
   "view":"第三人称/横版", "actions":["探索","解谜","收集","对话","机关","线索","解锁"],
   "loop":["探索场景","发现谜题/线索","使用道具/解谜","解锁新区域","推进剧情"],
   "mech":[("解谜系统","谜题/机关/线索"),("道具系统","关键道具收集与使用"),("剧情系统","对话/冒险推进")]},

  {"name":"恐怖/生存", "kws":["逃跑","躲避","追杀","手电","钥匙","怪物","隐藏","存档","惊吓","血条"],
   "view":"第一/第三人称", "actions":["逃跑","躲避","探索","解谜","收集","战斗"],
   "loop":["探索环境","躲避/逃离怪物","收集道具/钥匙","解开谜题","逃出生天"],
   "mech":[("生存系统","血量/弹药/资源管理"),("潜行系统","躲避/隐藏"),("解谜系统","钥匙/机关")]},

  {"name":"战棋/SLG", "kws":["移动","攻击范围","占领","部队","兵种","地形","城池","招募","内政","谋略"],
   "view":"俯视/网格", "actions":["移动","攻击","占领","招募","升级","内政"],
   "loop":["移动部队","占领/攻击","内政发展","招募升级","推进战局"],
   "mech":[("战棋系统","移动/攻击范围/兵种"),("内政系统","城池/资源/招募")]},

  {"name":"平台跳跃", "kws":["跳跃","平台","障碍","冲刺","踩","旗","关卡","二段跳","金币","陷阱"],
   "view":"横版", "actions":["跳跃","冲刺","收集","躲避","踩"],
   "loop":["控制角色移动","跳跃越过障碍","收集金币/道具","到达关卡终点","（继续下关）"],
   "mech":[("跳跃系统","跳跃/二段跳/冲刺"),("关卡系统","障碍/平台/收集物")]},
]

# 计算每种类型的命中分
joinall = "".join(all_texts)
def genre_score(g, texts):
    return sum(1 for t in texts for kw in g["kws"] if kw in t)
scored = [(g, genre_score(g, all_texts)) for g in GENRES]
scored.sort(key=lambda x: -x[1])
matched = [(g, s) for g, s in scored if s > 0]

if matched:
    top_g, top_s = matched[0]
    game_type = top_g["name"] + (f"（兼有 {matched[1][0]['name']} 特征）" if len(matched) > 1 and matched[1][1] > 0 else "")
    best_genre = top_g
else:
    game_type = "未能明确判断（OCR 关键词未命中已知类型，建议启用视觉大模型 GAME_LLM_API_KEY 或人工确认）"
    best_genre = None

# 5.2 视角：优先用匹配类型的视角，再按通用关键词微调
if best_genre:
    视角 = best_genre["view"]
else:
    视角 = "未知"
if any(k in joinall for k in ["准星","瞄准镜","第一人称"]):
    视角 = "第一人称（FPS）"
elif any(k in joinall for k in ["竖屏","挂机","离线","收益"]) and "竖屏" not in 视角:
    视角 = "竖屏手游"

# 5.3 动作词频（合并所有类型的动作词，构成全局统计）
ACTION_KW = sorted(set(kw for g in GENRES for kw in g["actions"]))
act_counter = Counter()
for t in all_texts:
    for kw in ACTION_KW:
        if kw in t:
            act_counter[kw] += 1
top_actions = [a for a, _ in act_counter.most_common(12)]

# 5.4 核心循环：用匹配类型的 loop（数据驱动，通用）；匹配不到则用高频动作兜底
if best_genre:
    base_loop = best_genre["loop"][:]
else:
    if top_actions:
        base_loop = top_actions[:5] + ["（继续循环）"]
    else:
        base_loop = ["（OCR 信息不足，建议启用视觉大模型或人工补充核心循环）"]

# 5.5 UI 元素识别（通用 UI 关键词库）
UI_KW = {"任务/目标追踪":["任务","主线","支线","目标","追踪","日常","剧情"],
         "装备/背包":     ["装备","背包","物品","武器","护甲","神器","饰品","法宝","道具栏"],
         "数值/货币面板": ["HP","MP","血量","蓝量","经验","等级","属性","金币","元宝","灵石","铜钱","钻石","分数","得分"],
         "技能/战斗":     ["技能","快捷","冷却","必杀","大招","伤害","暴击","连招","弹药","护甲值"],
         "养成/强化":     ["强化","升星","镶嵌","熔炼","炼制","炼器","突破","修炼","境界","升级","天赋","改装"],
         "地图/导航":     ["地图","小地图","方向","导航","坐标","传送","地点"],
         "社交/多人":     ["宗门","帮派","好友","聊天","组队","招募","公会","对战","匹配"],
         "系统/导航":     ["设置","菜单","返回","确认","商店","活动","签到","背包","退出"]}
ui_found = {}
for ui_name, kws in UI_KW.items():
    hit = sorted(set(k for k in kws if any(k in t for t in all_texts)))
    if hit:
        ui_found[ui_name] = hit[:6]

# 5.6 节奏时间轴（6 段）
SEG = 6
seg_len = DUR / SEG if DUR > 0 else 1
timeline = []
for s in range(SEG):
    lo, hi = s * seg_len, (s + 1) * seg_len
    seg_texts = [t for r in ocr_results if lo <= r["t"] < hi for t, _ in r["texts"]]
    seg_type = "（数据较少）"
    if seg_texts:
        seg_scored = [(g["name"], genre_score(g, seg_texts)) for g in GENRES]
        seg_scored.sort(key=lambda x: -x[1])
        if seg_scored[0][1] > 0:
            seg_type = seg_scored[0][0].split("/")[0]
    seg_c = Counter()
    for t in seg_texts:
        for kw in ACTION_KW:
            if kw in t:
                seg_c[kw] += 1
    hot = "、".join([k for k, _ in seg_c.most_common(5)]) or "（无明显关键词）"
    timeline.append((s + 1, lo, hi, seg_type, hot))

# ------------------------------------------------------------------
# 阶段 5b：视觉大模型增强（可选）
# ------------------------------------------------------------------
LLM = None
api_key = os.environ.get("GAME_LLM_API_KEY")
if api_key:
    base_url = os.environ.get("GAME_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("GAME_LLM_MODEL", "gpt-4o")
    print(f"      [LLM] 调用视觉大模型增强 ({model}) ...")

    cand = sample[:]
    if len(cand) > LLM_MAX_IMAGES:
        step = len(cand) / LLM_MAX_IMAGES
        cand = [cand[int(i * step)] for i in range(LLM_MAX_IMAGES)]

    images_b64 = []
    for t, name in cand:
        p = os.path.join(SRC_FRAME_DIR, name)
        with open(p, "rb") as fp:
            images_b64.append((t, base64.b64encode(fp.read()).decode()))

    ocr_summary = []
    for r in ocr_results:
        if r["texts"]:
            txts = " | ".join([t for t, _ in r["texts"][:6]])
            ocr_summary.append(f"[{r['name']}] {txts}")
    ocr_summary_text = "\n".join(ocr_summary[:50]) or "（无 OCR 文字）"

    prompt = (
        "你是资深游戏分析师。下面给你一段游戏游玩视频按时间顺序的关键帧图片和它们的 OCR 文字摘要。"
        "请基于画面与文字，深度分析这款游戏，严格只输出下面的 JSON（中文），不要输出 JSON 以外的内容：\n"
        "{\n"
        '  "游戏名称": "若能识别则填写，否则填 未知",\n'
        '  "游戏类型": "例如 放置修仙RPG / ARPG / FPS 等",\n'
        '  "视角": "竖屏/横屏 + 第一/第三人称 等",\n'
        '  "总体玩法": "3-5 句话描述玩家在游戏里主要做什么、目标是什么",\n'
        '  "核心机制": ["机制1","机制2",...],\n'
        '  "核心循环": ["步骤1","步骤2","步骤3",...],\n'
        '  "画面UI元素": ["元素1","元素2",...],\n'
        '  "节奏分析": "对游玩节奏/阶段变化的简要分析"\n'
        "}\n\n"
        f"OCR 文字摘要：\n{ocr_summary_text}\n"
    )

    content = [{"type": "text", "text": prompt}]
    for t, b64 in images_b64:
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

    payload = {"model": model, "messages": [{"role": "user", "content": content}],
               "temperature": 0.3, "max_tokens": 1800}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    req = urllib.request.Request(base_url + "/chat/completions",
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        ans = data["choices"][0]["message"]["content"]
        m = re.search(r"\{[\s\S]*\}", ans)
        if m:
            LLM = json.loads(m.group(0))
            print("      [LLM] 增强分析完成")
        else:
            print("      [LLM] 未返回有效 JSON，回退本地基线")
    except Exception as e:
        print(f"      [LLM] 调用失败: {e}，回退本地基线")
else:
    print("      [LLM] 未设置 GAME_LLM_API_KEY，仅用本地基线")

# ------------------------------------------------------------------
# 阶段 6：组装 Markdown
# ------------------------------------------------------------------
print("[6/6] 组装 Markdown 报告 ...")
ts_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
out_md = os.path.join(OUT_DIR, f"game_report_{ts_str}.md")

if LLM:
    md_名称 = LLM.get("游戏名称", "未知")
    md_类型 = LLM.get("游戏类型", game_type)
    md_视角 = LLM.get("视角", 视角)
    md_玩法 = LLM.get("总体玩法", None)
    md_机制 = LLM.get("核心机制", []) or []
    md_循环 = LLM.get("核心循环", base_loop) or base_loop
    md_ui = LLM.get("画面UI元素", []) or []
    md_节奏 = LLM.get("节奏分析", "")
else:
    md_名称, md_类型, md_视角 = "未知", game_type, 视角
    md_玩法, md_机制, md_循环, md_ui, md_节奏 = None, [], base_loop, [], ""

if not md_机制:
    mech = []
    # 优先：用匹配类型的机制（数据驱动）
    if best_genre:
        for sys_name, sys_desc in best_genre["mech"]:
            mech.append(f"**{sys_name}**：{sys_desc}")
    else:
        # 兜底：跨类型通用机制关键词检测
        if any(k in joinall for k in ["装备","强化","炼制","炼器","升星","镶嵌","熔炼","改装"]):
            mech.append("**装备/强化系统**：装备获取、强化、升星、镶嵌等养成")
        if any(k in joinall for k in ["击败","技能","伤害","暴击","必杀","连招","瞄准","射击"]):
            mech.append("**战斗系统**：技能/伤害/暴击或射击等战斗要素")
        if any(k in joinall for k in ["金币","元宝","灵石","铜钱","钻石","分数","得分","购买","出售","商店","营业","利润"]):
            mech.append("**经济系统**：货币、交易、商店或经营收入")
        if any(k in joinall for k in ["任务","主线","支线","日常","目标","剧情"]):
            mech.append("**任务系统**：主线/支线/日常任务追踪")
        if any(k in joinall for k in ["挂机","自动","离线","收益"]):
            mech.append("**放置/挂机系统**：自动战斗、离线收益")
    md_机制 = mech if mech else ["（OCR 信息不足以细分机制，建议启用视觉大模型或人工补充）"]

if not md_ui:
    md_ui = [f"{k}（关键词：{'、'.join(v)}）" for k, v in ui_found.items()] or ["（未识别到典型 UI 文字）"]

if not md_玩法:
    if top_actions:
        loop_chain = " → ".join(base_loop[:5])
        md_玩法 = (f"从视频中可观察到玩家反复进行「{'、'.join(top_actions[:6])}」等活动，"
                   f"结合画面文字特征判断为 {md_类型}（视角：{md_视角}）。"
                   f"玩家主要通过【{loop_chain}】的循环推进游戏进度。")
    else:
        md_玩法 = "（OCR 提取的功能性文字较少，建议启用视觉大模型 GAME_LLM_API_KEY 或人工补充总体玩法描述。）"

circles = " → ".join([f"**{i+1}.{step}**" for i, step in enumerate(md_循环)]) if md_循环 else "（信息不足）"
mode = "本地基线" + (" + 视觉大模型增强" if LLM else "")

# 绘制核心循环环形图
loop_img_ref = None   # 写入 md 的图片引用（base64 内嵌 或 相对路径）
if md_循环:
    loop_png_name = f"core_loop_{ts_str}.png"
    loop_png = os.path.join(OUT_DIR, loop_png_name)
    print("      [图] 绘制核心循环环形图 ...")
    rp = draw_core_loop(md_循环, loop_png, title="核心循环")
    if rp:
        if EMBED_IMAGE:
            # 把图片转成 base64 直接内嵌进 md（单文件自包含，拷走也能显示）
            with open(loop_png, "rb") as fp:
                b64 = base64.b64encode(fp.read()).decode()
            loop_img_ref = f"![核心循环](data:image/png;base64,{b64})"
            print(f"      [图] 已内嵌 base64 ({len(b64)//1024}KB) -> md 自包含")
        else:
            loop_img_ref = f"![核心循环]({loop_png_name})"  # 相对路径（需图片同目录）

lines = []
A = lines.append
A(f"# 《{md_名称}》游玩分析报告\n")
A(f"> 生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
A(f"> 视频来源：`{video}`")
A(f"> 视频信息：时长 {DUR:.1f}s（{DUR/60:.1f}min）· {W}×{H} · 源 {FPS:.1f}fps")
A(f"> 抽帧：**一秒两帧（{FPS_SAMPLE} fps）**，共抽取 {ok} 帧；分析代表帧 {len(sample)} 张")
A(f"> 分析模式：{mode} · OCR 文本条目 {len(all_texts)}\n")
A("---\n")

A("## 一、游戏概述\n")
A(f"- **游戏名称**：{md_名称}")
A(f"- **游戏类型**：{md_类型}")
A(f"- **视角/形态**：{md_视角}")
A(f"- **总体玩法**：\n\n{md_玩法}\n")

A("## 二、核心循环\n")
A("玩家在游戏中反复执行的玩法动作链（核心体验闭环）：\n")
if loop_img_ref:
    A(f"{loop_img_ref}\n")
A(f"> {circles}\n")
if md_节奏:
    A(f"**节奏说明**：{md_节奏}\n")

A("## 三、核心机制\n")
for m in md_机制:
    A(f"- {m}")
A("")

A("## 四、画面与 UI 元素\n")
for u in md_ui:
    A(f"- {u}")
A("")

A("## 五、游玩节奏时间轴\n")
A("| 阶段 | 时间段 | 推测场景 | 高频关键词 |")
A("|------|--------|----------|-----------|")
for idx, lo, hi, seg_type, hot in timeline:
    A(f"| {idx} | {lo:.0f}s – {hi:.0f}s | {seg_type} | {hot} |")
A("")

A("## 六、高频动作词（OCR 统计）\n")
if top_actions:
    for a, c in act_counter.most_common(12):
        bar = "█" * min(24, c)
        A(f"- `{a}` ×{c}  {bar}")
else:
    A("- （未匹配到高频动作词）")
A("")

A("## 七、分析说明\n")
A(f"- **抽帧**：按一秒两帧（{FPS_SAMPLE} fps）共 {ok} 张照片（目录：`{SRC_FRAME_DIR}`）；"
  f"为控制 OCR 耗时，从中均匀采样 {len(sample)} 张代表帧进行分析。")
A(f"- **数据来源**：PaddleOCR 提取文字共 {len(all_texts)} 条，"
  f"完整结果见 `report/ocr_results.json`。")
A(f"- **分析模式**：{mode}。" +
  ("视觉大模型对关键帧做了深度理解并合并结论。" if LLM else
   "未启用视觉大模型，结论基于关键词规则推断，可能存在偏差。如需更准确分析，请设置环境变量 GAME_LLM_API_KEY 后重跑。"))
A("- **局限性**：OCR 仅能读取画面文字，无法理解纯视觉动作；场景/类型按文字关键词推断，可能与实际玩法有出入；核心循环与机制建议结合人工观看核对。")
A(f"- **产物目录**：`{OUT_DIR}`（关键帧目录：`{SRC_FRAME_DIR}`、`report/ocr_results.json`、本 md）。\n")

with open(out_md, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"\n✅ done -> {out_md}")
print(f"   抽帧/复用 {ok} 张 -> {SRC_FRAME_DIR}")
print(f"   OCR 结果 -> {REPORT_DIR}\\ocr_results.json")

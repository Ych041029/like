# -*- coding: utf-8 -*-
"""
================================================================================
 通用版游戏主线任务自动分析工具 (AI自动化版)
================================================================================
设计为"AI当司机"模式：
  用户把视频+本脚本发给AI助手 → AI用云端视觉确认面板位置 → AI用--panel传坐标
  → 本脚本用本地PaddleOCR批量精确读字 → 输出任务时间线MD表格

输入：视频(.mp4) 或 单张图片(.jpg/.png)
输出：主线任务时间线表格(.md + .csv) + 原始OCR(.txt)

使用:
  # 完整分析(AI确认面板坐标后用)
  python 游戏任务分析.py "视频.mp4" --panel 25,720,210,90

  # 自动定位(不传--panel,脚本自己找面板,适合已知游戏)
  python 游戏任务分析.py "视频.mp4"

  # 诊断模式(只抽帧+OCR+导出原始结果,AI先看本地OCR能不能读出字)
  python 游戏任务分析.py "视频.mp4" --diagnose

  # 单张图片(快速测试某一帧OCR效果)
  python 游戏任务分析.py "某帧.jpg"

  # 调整放大倍数(新游戏字体小/识别率低时调高)
  python 游戏任务分析.py "视频.mp4" --scale 3

  # 任务名在进度【下方】的游戏(如神器传说布局"进度在上、名在下")
  python 游戏任务分析.py "视频.mp4" --panel 25,744,185,48 --task-below --scale 3

  # 出表格后自动核查漏任务(读到了名但被规则过滤的任务, 列清单供人工核对)
  #   默认开启。可用 --no-audit-missed 关闭, --audit-min-count N 调噪声阈值

依赖: paddlepaddle paddleocr pillow numpy ; 需要 ffmpeg 在 PATH
环境(本机已装): Python3.10=C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python310\\python.exe
                ffmpeg=C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe
================================================================================
"""
import os, sys, re, subprocess, argparse
from collections import Counter

os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# ============ 按需修改区(换新游戏时, 如果有按钮/弹窗文字混进来, 加到这里) ============
# 注意: 黑名单多一点没坏处(只要不误杀真实任务名)。以下词覆盖了多款游戏的常见按钮/弹窗。
# 【修复】分两类: 长短语(子串匹配,误杀风险低) + 短按钮词(精确匹配,避免误杀任务名)。
#   旧版"出售/装备"用子串匹配,会误杀"通过出售装备获得金币""出售1件装备"等真任务。
#   短词(≤2字)改为"整行去掉标点后等于该词"才排除,任务名包含短词不再被误杀。
NOT_TASK = ["装备后自动出售","出售原装备","当前装备","自动出售","新获得","让我们再",
    "以后就能","还有很多材料","师兄加油","出售后不仅","点击","继续","确定","取消",
    "关闭","前往","传送","完成","完成14个","完成个主线","个主线","主线任务","支线任务",
    "级解锁","升级所需时间","升级炼器鼎","每日登录","每日可领取","炼器鼎升级礼包",
    "结识仙友","山海挑战","开启炼器加速","法相升级","提升属性","提升黑性","法天象地",
    "阵法效果","超值礼包","斗法令","多倍炼器","质量","高于","注成","拒绝","阅读",
    "日志","彩头","礼包","用户隐私","隐私保护","保护提示",
    # ---- 通用按钮/弹窗(多游戏共用): 短词移到NOT_TASK_SHORT精确匹配 ----
    "公告","声明","休战","结算","充值","福利","签到","领奖",
    # ---- 疯狂骑士团 特有非任务UI(关卡结算/装备弹窗/系统菜单) ----
    "通关奖励","定制史诗","后续版本","选择服务器","停用角色","钻石骑士",
    "城府T13","总是保持以上选择","游戏账号信息","开启离线开宝箱","仅此一次",
    "详细信息","指南",
    "优秀的]","[普通的","[优秀的","普通的]","[精良的","精良的]",
    # ---- 竞技场玩家名/服务器名残留(本视频固定反复出现) ----
    "秋鸿雁","(3265股","(3265服","3265服","股）","等级40","宝箱等级6",
    "附康最","附庭最","附最高","附魔最高"]

# 短按钮词(≤2字): 用精确匹配(整行去标点后==该词才排除), 不因子串包含而误杀任务名。
# 例: "装备""出售"是按钮, 但"出售1件装备""通过出售装备获得金币"是真任务, 不能误杀。
NOT_TASK_SHORT = ["返回","设置","背包","商店","出售","装备","邮件","好友","排行","公会",
    "活动","骑士团","钓鱼","副本","领地","菜单"]

def is_blacklisted(txt):
    """统一黑名单判定(修复误杀真任务)。
    - 长短语(NOT_TASK): 子串包含即排除(够长,误杀风险低)
    - 短按钮词(NOT_TASK_SHORT): 整行去标点后==该词才排除(避免误杀含这些词的任务名)"""
    if not txt: return True
    # 1. 长短语子串匹配
    for b in NOT_TASK:
        if b in txt: return True
    # 2. 短按钮词精确匹配: 去掉标点/空白后整行相等才算
    bare = norm_desc(txt)
    for b in NOT_TASK_SHORT:
        if bare == b: return True
    return False

# 任务动词(用于自动定位面板的备选, 以及辅助判断哪些文字是任务名)
TASK_KW = ["装备","穿着","穿戴","炼制","出售","击败","升级","强化","采集","寻找","对话",
    "交谈","到达","探索","击杀","收集","交付","领取","解锁","修炼","突破","招募","建造",
    "护送","激活","开启","挑战","通关","完成","试炼","进行","斗法","炼器","熔炼","觉醒",
    "进阶","升星","镶嵌","合成","提升","境界","等级","通过","进入","学习",
    # ---- 补充动词(适配更多游戏) ----
    "打开","宝箱","寻路","移动","前进","查看","跟随","引导","签到","登录",
    "攻击","防御","逃跑","捕捉","驯服","种植","烹饪","锻造","附魔","分解",
    "巡逻","驻守","支援","突围","潜伏","侦查","占领","守护","运输","剿灭"]
# =====================================================================================

PROG_RE = re.compile(r'\(?\s*(\d{1,4})\s*/\s*(\d{1,4})\s*\)?')

def norm_desc(s):
    if not s: return ""
    return re.sub(r'[\(\)/\[\]【】！。，、\s·\-]+', '', s)

def task_name_only(s):
    """剥掉任务文字里的进度数字(X/Y),只留任务名部分。
    用于判断'打开宝箱(0/1)'和'打开宝箱(1/1)'是同一任务(进度变了,任务没变)。"""
    if not s: return ""
    return PROG_RE.sub('', s).strip()

def safe_align(base, candidate):
    """【安全对齐】判断candidate是否是base的OCR错字版本(可对齐到base)。
    核心原则: 只在"明确是OCR错字"时才对齐, 任何可能是真切换的情况都不对齐。
    这样保证: 治切碎的同时, 绝不漏任务(绝不把两个不同任务合并)。

    对齐条件(全部满足才对齐, 任一不满足就返回False=不对齐):
    1. 两者都有内容, 且剥掉进度后比任务名
    2. 长度相同(不同=可能漏字或不同任务, 危险, 不对齐)
    3. 差异≤2个字(差异大=可能不同任务, 危险, 不对齐)
    4. 首字必须相同(首字不同=动词不同, 大概率不同任务, 不对齐)
    5. 数字部分必须一致(数字不同=如1个vs3个, 绝对是不同任务, 不对齐)
    """
    if not base or not candidate: return False
    nb = task_name_only(base)
    nc = task_name_only(candidate)
    if not nb or not nc: return False
    # 条件2: 长度必须相同
    if len(nb) != len(nc): return False
    # 条件4: 首字必须相同(防动词不同的不同任务被合并)
    if nb[0] != nc[0]: return False
    # 条件5: 数字部分必须一致(从原文提取所有数字序列比较)
    digits_b = re.findall(r'\d+', base)
    digits_c = re.findall(r'\d+', candidate)
    if digits_b != digits_c: return False
    # 条件3: 差异≤2个字
    diff = sum(1 for cb, cc in zip(nb, nc) if cb != cc)
    if diff > 2: return False
    return True

def edit_dist(a, b):
    la, lb = len(a), len(b)
    if la == 0: return lb
    if lb == 0: return la
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i-1] == b[j-1] else 1
            cur[j] = min(prev[j] + 1, cur[j-1] + 1, prev[j-1] + cost)
        prev = cur
    return prev[lb]

def similar(d1, d2):
    a, b = norm_desc(d1), norm_desc(d2)
    if not a or not b: return False
    if a == b or a in b or b in a: return True
    # 【数字判据·宽松版】治"漏任务": 打开1个宝箱 vs 打开3个宝箱 是不同任务,不能合并。
    # 但要避免误伤"推进中": 同一任务进度从 1/5→3/5 时, 数字变了但分母(总数)没变 → 仍判同任务。
    da = re.findall(r'\d+', d1)
    db = re.findall(r'\d+', d2)
    if da and db:
        # 两边都有数字: 比"最大数字"(通常是任务总数/分母)。
        # 分母不同=真不同任务(如1个vs3个宝箱),拆。
        # 分母相同=同任务推进中(如1/5 vs 3/5),不拆,走后续相似度。
        denom_a = max(int(x) for x in da)
        denom_b = max(int(x) for x in db)
        if denom_a != denom_b:
            return False
    if a[0] == b[0]:
        return edit_dist(a, b) / max(len(a), len(b)) <= 0.4
    a2, b2 = a[1:], b[1:]
    if not a2 or not b2: return False
    return edit_dist(a2, b2) <= 0

def is_exp_bar(txt, num, den):
    stripped = re.sub(r'[\(\)\[\]【】\s]', '', txt)
    return bool(re.fullmatch(r'[\d/]+', stripped)) and (60 <= den <= 90)

def is_dialogue(txt):
    return len(txt) >= 6 and any(p in txt for p in '。，！？；：、…')

# 角色属性字段名(详情弹窗里的"速度：/攻击："等,带冒号,不是任务)。任务名从不含冒号。
ATTR_WORDS = ["速度","生命","攻击","防御","吸血","反击","连击","闪避","暴击","击晕",
    "忽视暴击","忽视闪避","忽视吸血","忽视反击","忽视连击","战力","幸运","韧性","穿透","免伤"]
# 竞技场/排行榜/好友列表特征词(出现这些说明面板被此类界面遮挡,任务应置空走补全)
RANK_NOISE = ["积分","服）","服)","服】","服]","挑战券","刷新列表","消息"]

def is_noise_task(txt):
    """判定面板内某行文字是不是噪声(属性/排行/玩家名),而不是真任务。
    疯狂骑士团这类游戏的真任务名特征: 无冒号、无"服)"、不是纯属性字段。"""
    if not txt: return True
    # 1. 含冒号(全角或半角) -> 属性字段"速度："或"积分："等,绝非任务
    if '：' in txt or ':' in txt: return True
    # 2. 含服务器标记 "(3265服)" "(3265服）"
    if any(s in txt for s in ["服）","服)","服】","服]"]): return True
    # 3. 纯属性字段(去标点后恰好是某个属性词)
    bare = re.sub(r'[：:0-9%\+\-\s]+','',txt)
    if bare in ATTR_WORDS: return True
    # 4. 玩家等级标记 "Lv.13" "Lvs13" 这类(常出现在排行/详情行)
    if re.search(r'lv\.?\s*\d', txt, re.I): return True
    return False

def filename_to_time(name):
    m = re.match(r'(\d+)分(\d{1,2})秒_第(\d)帧', name)
    return f"{int(m.group(1))}:{int(m.group(2)):02d}" if m else name

def sort_key(name):
    m = re.match(r'(\d+)分(\d{1,2})秒_第(\d)帧', name)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (99,99,99)

# ============ 第1步: 抽帧 ============
def extract_frames(video, out_dir, fps=2):
    os.makedirs(out_dir, exist_ok=True)
    r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                        "-of","default=noprint_wrappers=1:nokey=1",video],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    total_sec = int(float(r.stdout.strip()))
    files = []; step = 1.0 / fps
    for sec in range(total_sec):
        mm, ss = sec // 60, sec % 60
        for n in range(1, fps + 1):
            ts = sec + (n - 1) * step
            name = f"{mm}分{ss:02d}秒_第{n}帧.jpg"
            path = os.path.join(out_dir, name)
            subprocess.run(["ffmpeg","-nostdin","-y","-ss",f"{ts:.3f}","-i",video,
                            "-frames:v","1","-q:v","2",path,"-loglevel","error"],
                           check=False, stdin=subprocess.DEVNULL)
            if os.path.exists(path): files.append(name)
        if (sec + 1) % 60 == 0: print(f"  抽帧: {sec+1}/{total_sec}秒", flush=True)
    print(f"  抽帧完成: {len(files)}帧", flush=True)
    return files

# ============ 第2步: 整图OCR (scale可调,新游戏字体小可调高) ============
def ocr_all_frames(frame_dir, files, scale=2):
    from paddleocr import PaddleOCR
    from PIL import Image
    import numpy as np
    ocr = PaddleOCR(use_angle_cls=False, lang='ch', show_log=False)
    results = {}; total = len(files)
    for i, f in enumerate(files):
        try:
            im = Image.open(os.path.join(frame_dir, f)).convert("RGB")
            im2 = im.resize((im.width*scale, im.height*scale))
            res = ocr.ocr(np.asarray(im2), cls=False)
        except Exception:
            res = None
        texts = []
        if res and res[0]:
            for line in res[0]:
                txt=line[1][0]; sc=round(line[1][1],3); box=line[0]
                xs=[p[0] for p in box]; ys=[p[1] for p in box]
                cx=(min(xs)+max(xs))/2/scale; cy=(min(ys)+max(ys))/2/scale
                texts.append((txt,sc,cx,cy))
        results[f]=texts
        if (i+1)%100==0: print(f"  OCR: {i+1}/{total}", flush=True)
    print(f"  OCR完成: {total}帧 (放大{scale}x)", flush=True)
    return results

# ============ 复用OCR缓存(改逻辑后快速验证,不重跑OCR) ============
def load_ocr_cache(path):
    """加载带坐标的OCR缓存。兼容两种格式:
       - 新格式: 文件名\\t文本(0.99)@[104,521] | 文本(0.95)@[110,537]
       - 旧格式: 文件名\\t文本(0.99) | 文本(0.95)        (无坐标时cx=cy=0)
    返回 (ocr_results字典, files列表)
    """
    import re as _re
    results={}; files=[]
    # 匹配 "文本(置信度)@[cx,cy]" 或 "文本(置信度)"
    item_re=_re.compile(r'(.*?)\(([0-9.]+)\)(?:@\[(\d+),(\d+)\])?')
    for ln in open(path,encoding='utf-8').read().splitlines():
        if '\t' not in ln: continue
        fn,rest=ln.split('\t',1)
        texts=[]
        for m in item_re.finditer(rest):
            txt=m.group(1).strip()
            if not txt: continue
            sc=float(m.group(2))
            cx=int(m.group(3)) if m.group(3) else 0
            cy=int(m.group(4)) if m.group(4) else 0
            texts.append((txt,sc,float(cx),float(cy)))
        results[fn]=texts
        files.append(fn)
    return results, files

# ============ 第3步: 自动定位(只用进度数字,不被弹窗污染) ============
def auto_detect_panel(files, ocr_results):
    prog_hits=[]; kw_hits=[]
    step=max(1,len(files)//25); samples=files[::step][:25]
    for f in samples:
        for txt,sc,cx,cy in ocr_results.get(f,[]):
            m=PROG_RE.search(txt)
            if m:
                num,den=int(m.group(1)),int(m.group(2))
                if not is_exp_bar(txt,num,den): prog_hits.append((cx,cy)); continue
            if any(k in txt for k in TASK_KW) and not is_blacklisted(txt):
                kw_hits.append((cx,cy))
    hits=prog_hits if len(prog_hits)>=3 else (prog_hits+kw_hits)
    if len(hits)<3: return None
    import numpy as np
    xs=np.array([h[0] for h in hits]); ys=np.array([h[1] for h in hits])
    cx_m,cy_m=float(np.median(xs)),float(np.median(ys))
    W=float(xs.max())+50; H=float(ys.max())+50
    print(f"  (进度{len(prog_hits)}处, 动词{len(kw_hits)}处)", flush=True)
    return (max(0,int(cx_m-W*0.20)), max(0,int(cy_m-H*0.06)),
            min(int(W*0.45),int(W)-max(0,int(cx_m-W*0.20))),
            min(int(H*0.14),int(H)-max(0,int(cy_m-H*0.06))))

# ============ 第4步: 提取任务信息(进度锚点+正上方多行拼接) ============
def extract_task_info(texts, panel_box, exp_y=None, below=False):
    """【融合漏检修复核心思路·通用版】
    核心改进(治问题2奖励行误识 + 问题1漏任务的长名读不全):
      1. 进度是任务的真实锚点: 只采信"有进度(X/Y)"的帧; 无进度=面板被遮挡 → 置空走补全
      2. 任务名=进度正上方、cx相近的多个汉字行【拼接】(不再取"最靠下"那行)
         —— 这样"通过出售装备"+"获得5金币"能拼回完整句,且奖励行不会单独冒充任务
      3. 经验条用【坐标】排除(不靠分母范围): exp_y参数=经验条y范围, 不写死y528-550
    panel_box: --panel传进来的框(框住任务名行+进度行两行)
    exp_y: (y_min,y_max)经验条所在y范围, None则用旧分母判据兜底
    below: 任务名在进度【下方】时为True(默认False=上方, 兼容原行为)。
           某些游戏(如神器传说)任务面板布局是"进度在上、任务名在下",
           此时需 below=True 才能在进度下方找到任务名行。
    """
    px,py,pw,ph=panel_box
    inside=[(txt,sc,cx,cy) for txt,sc,cx,cy in texts
            if px<=cx<=px+pw and py<=cy<=py+ph]

    def _is_exp(txt, num, den):
        """经验条判据: 优先用坐标(exp_y)排除; 无坐标则用旧分母范围兜底。"""
        if exp_y:
            # 这条文字的y若落在经验条y范围 → 经验条, 排除
            for txt2,sc2,cx2,cy2 in inside:
                if txt2==txt and exp_y[0]<=cy2<=exp_y[1]:
                    return True
            return False
        return is_exp_bar(txt, num, den)

    # ---- 第1步: 在面板内找进度行(真实任务的锚点) ----
    prog=None; pcy=None; pcx=None
    for txt,sc,cx,cy in inside:
        m=PROG_RE.search(txt)
        if m and sc>=0.55:
            num,den=int(m.group(1)),int(m.group(2))
            if not _is_exp(txt,num,den):
                prog=(num,den); pcy=cy; pcx=cx; break
    # 【只采信有进度的帧】: 无进度 = 面板被遮挡/未显示 → 置空, 交给遮挡补全
    if prog is None:
        return None,None

    # ---- 第2步: 任务名 = 进度侧(cx相近)的多个汉字行拼接 ----
    # below=False(默认): 任务名在进度【上方】(原行为, 适配疯狂骑士团等)
    # below=True       : 任务名在进度【下方】(适配神器传说等"进度在上名在下"布局)
    upper=[]
    for txt,sc,cx,cy in inside:
        if not below:
            # 默认: 必须明显在进度上方(cy比进度小), 且cx相近(同行)
            if cy >= pcy-3: continue          # 不在进度上方
            if pcy - cy > 40: continue        # 太高(>40px), 可能是面板外的UI
        else:
            # below模式: 必须明显在进度下方(cy比进度大), 且cx相近(同行)
            if cy <= pcy+3: continue          # 不在进度下方
            if cy - pcy > 40: continue        # 太低(>40px), 可能是面板外的UI
        if abs(cx-pcx) > 80: continue      # cx偏移过大, 不是同一行文字
        if len(norm_desc(txt)) < 2: continue
        if not re.search(r'[\u4e00-\u9fff]', txt): continue  # 无汉字
        if is_blacklisted(txt): continue
        if is_noise_task(txt): continue
        if is_dialogue(txt): continue
        if PROG_RE.search(txt): continue   # 进度行本身, 跳过
        # 清洗OCR把面板竖分隔符切成独立块/空格的残留
        clean = re.sub(r'[\|｜]', '', txt).strip()
        if not clean: continue
        upper.append((cy,sc,clean))

    if upper:
        # 按y从高到低(距进度近→远)排序后翻转, 再去重(互为子串的只留长的)
        upper.sort(key=lambda x:-x[0])
        parts=[t for _,_,t in upper][::-1]
        uniq=[]
        for p in parts:
            if p not in uniq and not any(p in u or u in p for u in uniq):
                uniq.append(p)
        joined = "".join(uniq)
        # 最终清洗: 去掉拼接后可能残留的空白/分隔符
        joined = re.sub(r'[\s\|｜]+', '', joined)
        return joined, prog
    # 有进度但任务名行没读到(被瞬时遮挡): 返回None, 走遮挡补全向前借
    return None, prog

# ============ 第5步: 还原时间线 ============
def build_timeline(files, ocr_results, panel_box, fps, exp_y=None, below=False):
    n=len(files)
    raw_desc=[None]*n; raw_prog=[None]*n
    for i,f in enumerate(files):
        d,p=extract_task_info(ocr_results.get(f,[]),panel_box,exp_y,below=below)
        raw_desc[i]=d; raw_prog[i]=p

    # 【安全对齐】(治切碎: OCR读错但像基准 -> 对齐到基准)
    # 核心原则: 只在"明确是OCR错字"时对齐, 绝不把不同任务合并(绝不漏任务)
    # 基准 = 上一个"无法对齐到更早基准"的任务(即真切换点)
    # 遮挡的帧(None)跳过, 交给后面的遮挡补全处理
    desc = list(raw_desc)
    current_base = None  # 当前基准任务名
    for i in range(n):
        if desc[i] is None:
            continue  # 遮挡帧, 交给后面遮挡补全
        if current_base is None:
            current_base = desc[i]  # 第一个任务, 建立基准
            continue
        # 这帧有任务文字, 跟当前基准比
        if safe_align(current_base, desc[i]):
            desc[i] = current_base  # 可安全对齐 -> 用基准替换(治切碎)
        else:
            current_base = desc[i]  # 不能对齐 = 真切换, 建立新基准

    # 【遮挡补全·保守版】(融合漏检修复优点③): 只在"前后是同一任务"时才补全。
    # 关键修正: 前后不同任务时【留空】, 不硬填B。
    #   旧逻辑硬填B会导致: A任务的遮挡空帧假性延续成B, 吞掉中间的真任务(漏任务的元凶之一)。
    #   新逻辑留空 = 承认这里是真实任务切换断点, 不臆造。
    def nearest_prev_task(i):
        for j in range(i-1,-1,-1):
            if raw_prog[j] is not None and raw_desc[j]: return raw_desc[j]
        return None
    def nearest_next_task(i):
        for j in range(i+1,n):
            if raw_prog[j] is not None and raw_desc[j]: return raw_desc[j]
        return None
    for i in range(n):
        if desc[i] is not None: continue
        # 【有效帧但任务名缺失】(进度读到了、任务名没读到): 向前借同任务名
        if raw_prog[i] is not None:
            desc[i]=nearest_prev_task(i)
            continue
        # 【空帧(面板被遮挡)】: 只在前后是同任务时才补全
        A=nearest_prev_task(i); B=nearest_next_task(i)
        if A and B and similar(task_name_only(A), task_name_only(B)):
            desc[i]=A                         # 同任务被短暂遮挡 → 沿用前任务
        elif A and B is None:
            desc[i]=A                         # 后面再无任务 → 延续前任务到结尾
        # 否则留空(前后不同任务 = 真实切换断点, 不硬填)

    dens=[raw_prog[i][1] if raw_prog[i] else None for i in range(n)]
    for i in range(n):
        if dens[i] is not None: continue
        for j in range(i-1,-1,-1):
            if raw_prog[j] is not None: dens[i]=raw_prog[j][1]; break

    segs=[]; start=0
    for i in range(1,n):
        if desc[i] and desc[start] and not similar(desc[i],desc[start]):
            segs.append([start,i-1]); start=i
        elif desc[i] and not desc[start]: start=i
    segs.append([start,n-1])

    def seg_prog(a,b):
        ps=[raw_prog[k] for k in range(a,b+1) if raw_prog[k]]
        return (ps[0],ps[-1]) if ps else (None,None)
    merged=[]
    for a,b in segs:
        nd=[desc[k] for k in range(a,b+1) if desc[k]]
        rep=Counter(nd).most_common(1)[0][0] if nd else ""
        if merged:
            pa,pb=merged[-1]
            pnd=[desc[k] for k in range(pa,pb+1) if desc[k]]
            prep=Counter(pnd).most_common(1)[0][0] if pnd else ""
            same=rep and prep and similar(prep,rep)
            if not same:
                _,pl=seg_prog(pa,pb); cf,_=seg_prog(a,b)
                if pl and cf and pl[1]==cf[1] and cf[0]>=pl[0]: same=True
            if same: merged[-1][1]=b; continue
        merged.append([a,b])

    # 孤立段丢弃(带进度保护·借鉴漏检修复)
    # 【修复】旧逻辑"段长<=2且与前后不相似→丢弃"会误杀瞬间完成的真任务(如穿戴5件装备5/5,
    #       只显示1-2秒)。修正: 带进度数字的短段是真实任务, 不当噪声丢弃。
    #       只有"既短又无任何进度证据且与前后不相似"才视为噪声。
    if len(merged) > 2:
        cleaned=[merged[0]]
        for i in range(1,len(merged)-1):
            a,b=merged[i]; seg_len=b-a+1
            cd=[desc[k] for k in range(a,b+1) if desc[k]]
            cr=Counter(cd).most_common(1)[0][0] if cd else ""
            pa,pb=cleaned[-1]
            pd_=[desc[k] for k in range(pa,pb+1) if desc[k]]
            pr=Counter(pd_).most_common(1)[0][0] if pd_ else ""
            na,nb=merged[i+1]
            nd_=[desc[k] for k in range(na,nb+1) if desc[k]]
            nr=Counter(nd_).most_common(1)[0][0] if nd_ else ""
            # has_prog: 这段是否有真实进度数字(有进度=真任务, 不丢)
            has_prog = any(raw_prog[k] is not None for k in range(a,b+1))
            if seg_len<=2 and cr and pr and nr and not has_prog:
                if not similar(cr,pr) and not similar(cr,nr):
                    cleaned[-1][1]=b; continue
            cleaned.append(merged[i])
        cleaned.append(merged[-1])
        merged=cleaned

    timeline=[]
    for a,b in merged:
        descs=[desc[k] for k in range(a,b+1) if desc[k]]
        if descs:
            cnt=Counter(descs); top=cnt.most_common(1)[0][1]
            cands=[x for x,c in cnt.items() if c==top]
            d=max(cands, key=lambda x: len(norm_desc(x)))
        else: d=""
        if not d: continue
        seg_dens=[dens[k] for k in range(a,b+1) if dens[k]]
        main_den=Counter(seg_dens).most_common(1)[0][0] if seg_dens else None
        pt=[]; ln=-1
        for k in range(a,b+1):
            p=raw_prog[k]
            if not p or (main_den is not None and p[1]!=main_den): continue
            if p[0]>ln:
                key=f"{p[0]}/{p[1]}"
                if not pt or pt[-1][0]!=key: pt.append((key,filename_to_time(files[k])))
                ln=p[0]
        timeline.append({"任务":d,"起帧":files[a],"止帧":files[b],
            "起时间":filename_to_time(files[a]),"止时间":filename_to_time(files[b]),"进度轨迹":pt})

    # 相邻任务推断
    timeline = infer_task_names(timeline)
    return timeline

def infer_task_names(timeline):
    """对残缺任务名做模板补全(单次顺序遍历, 边记边补)。"""
    import re as _re
    seen_suffix={}; seen_num2={}
    for t in timeline:
        name=t["任务"]
        if not name: continue
        m=_re.match(r'^(.+?)(\d+)$',name)
        if m and m.group(1) in seen_suffix:
            t["任务"]=f"{m.group(1)}{m.group(2)}{seen_suffix[m.group(1)]}"; name=t["任务"]
        m=_re.match(r'^(.+?)(\d+)-$',name)
        if m:
            for d in [0,-1,-2]:
                if (m.group(1),int(m.group(2))+d) in seen_num2:
                    t["任务"]=f"{m.group(1)}{m.group(2)}-{seen_num2[(m.group(1),int(m.group(2))+d)]+1}"; name=t["任务"]; break
        m=_re.match(r'^(.+?)(\d+)-(\d+)(.*)$',name)
        if m: seen_num2[(m.group(1),int(m.group(2)))]=int(m.group(3))
        else:
            m=_re.match(r'^(.+?)(\d+)(\D.*)?$',name)
            if m and m.group(3): seen_suffix[m.group(1)]=m.group(3)
    return timeline

# ============ OCR错字修正钩子(留空表, 不写死任何游戏错字) ============
# 设计: 漏检修复.py把疯狂骑士团的错字写死在fix()里(换游戏就失效)。
#   本通用版【不写死错字】, 留空表 + no-op函数。如需修字, 由AI清洗时动态填入此表,
#   或在调用export前对timeline做后处理。默认不修正, 保留OCR原文(可追溯)。
OCR_TYPO_FIX = {}  # 空: {"宝植":"宝箱", "排战":"挑战", ...} 需要时填, 默认不动
# 支持正则替换(用于"开头补字"等replace做不到的场景): 编译缓存
import re as _re_fix
_FIX_RE_CACHE = {}

def fix_ocr_typos(name, extra=None):
    """对单个任务名做错字修正。
    name: 任务名
    extra: 额外错字表 dict, 运行时动态传入(如AI清洗), 与全局OCR_TYPO_FIX合并。
    规则格式: {"错字":"正字"} 做replace; {"re:正则":"替换":} 做正则sub。
    默认no-op(空表时原样返回, 保留原文可追溯)。"""
    rules = {}
    if OCR_TYPO_FIX: rules.update(OCR_TYPO_FIX)
    if extra: rules.update(extra)
    if not rules or not name: return name
    r = name
    for wrong, right in rules.items():
        if isinstance(wrong, str) and wrong.startswith("re:"):
            # 正则替换: 键以"re:"开头
            pat = wrong[3:]
            if pat not in _FIX_RE_CACHE: _FIX_RE_CACHE[pat] = _re_fix.compile(pat)
            r = _FIX_RE_CACHE[pat].sub(right, r)
        else:
            r = r.replace(wrong, right)
    return r

# ============ 第6步: 输出 ============
def export(timeline, out_dir, name):
    md=[f"# 主线任务时间线 — {name}\n",
        "| # | 视频时间 | 主线任务 | 起止照片 | 进度变化（含完成时间点） |",
        "|---|---|---|---|---|"]
    for i,t in enumerate(timeline,1):
        prog=" → ".join(f"{p[0]}（{p[1]}）" for p in t["进度轨迹"]) if t["进度轨迹"] else "无"
        md.append(f"| {i} | {t['起时间']}~{t['止时间']} | {t['任务']} | {t['起帧']} ~ {t['止帧']} | {prog} |")
    md_text="\n".join(md)+"\n"
    mp=os.path.join(out_dir,f"主线任务时间线_{name}.md")
    cp=os.path.join(out_dir,f"主线任务时间线_{name}.csv")
    open(mp,"w",encoding="utf-8").write(md_text)
    import csv as _csv
    with open(cp,"w",encoding="utf-8-sig",newline="") as f:
        w=_csv.writer(f)
        w.writerow(["#","视频时间","主线任务","起止照片","进度变化"])
        for i,t in enumerate(timeline,1):
            prog=" → ".join(f"{p[0]}（{p[1]}）" for p in t["进度轨迹"]) if t["进度轨迹"] else "无"
            w.writerow([i,f"{t['起时间']}~{t['止时间']}",t["任务"],f"{t['起帧']} ~ {t['止帧']}",prog])
    print(f"\nMarkdown: {mp}\nCSV     : {cp}\n", flush=True)
    print(md_text, flush=True)

# ============ 漏任务候选核查(整理表格后): 找出"OCR读到名但被规则过滤"的任务 ============
def _miss_task_key(s):
    """漏任务归一化键(初筛): 用'数字骨架+汉字数'做粗键,
    把数字相同、长度相近的OCR变体先归到一类(如试炼1-6的各种错字版本)。
    后续再用编辑距离细合并。"""
    if not s: return ""
    s2 = PROG_RE.sub('', s)  # 去进度(X/Y)
    digits = re.findall(r'\d+', s2)
    digit_key = "-".join(digits) if digits else "X"
    han = re.sub(r'[^\u4e00-\u9fff]', '', s2)
    return f"{digit_key}|{len(han)}"

def _merge_by_editdist(groups):
    """对粗分组后的结果, 用编辑距离再做一轮合并。
    groups: list of {norm_key, samples, first, last, count}
    合并规则: 同一粗键下, 若两个样本的归一化(去标点)形式编辑距离<=2, 则合并。
    返回合并后的 groups。"""
    def _bare(s):
        s2 = PROG_RE.sub('', s)
        return re.sub(r'[^\u4e00-\u9fff0-9]', '', s2)
    merged = []
    for g in groups:
        bg = _bare(_pick_rep(g["samples"]))
        placed = False
        for m in merged:
            bm = _bare(_pick_rep(m["samples"]))
            # 数字骨架必须一致(防1-6并到1-8)
            if re.findall(r'\d+', bg) != re.findall(r'\d+', bm):
                continue
            # 长度相同且编辑距离<=2 -> 同一任务的OCR错字
            if len(bg) == len(bm) and edit_dist(bg, bm) <= 2:
                m["samples"].extend(g["samples"])
                m["first"] = min(m["first"], g["first"])
                m["last"] = max(m["last"], g["last"])
                m["count"] += g["count"]
                placed = True
                break
        if not placed:
            merged.append(dict(g))
    return merged

def _pick_rep(samples):
    """从样本里选出现次数最多的作代表(用于显示和比对)"""
    from collections import Counter
    c = Counter(samples)
    top = c.most_common(1)[0][1]
    cands = [s for s, n in c.items() if n == top]
    return max(cands, key=len)

def audit_missed_tasks(ocr_results, files, panel_box, timeline, out_dir, name, min_count=3):
    """扫描OCR原始数据, 找出"OCR读到了任务名、但没出现在最终时间线里"的候选漏任务。
    这类任务通常因为"OCR没读到进度数字"被脚本的'只采信有进度帧'规则丢弃。

    设计依据《新游戏分析使用手册》第六节: 漏任务先查证OCR读到没有, 再由人工核对原视频。
    本函数只负责"列出候选+精准时间点", 不自动加入时间线——是否加入由人工/AI决定。

    panel_box: 面板框(任务名行所在区域)
    timeline:  最终时间线(用于判断任务是否已被识别)
    min_count: 至少被OCR读到几次才算候选(过滤偶发OCR噪声)
    """
    px, py, pw, ph = panel_box
    # 1. 收集最终时间线里已有的任务(归一化), 用于排除已识别的
    have = set()
    for t in timeline:
        k = _miss_task_key(t.get("任务", ""))
        if k: have.add(k)

    # 2. 遍历所有帧, 收集面板内"任务名行"的文字
    #    任务名行: 在面板框内、含汉字、不是进度行
    raw_hits = {}  # norm_key -> {samples:[], first_idx, last_idx, count}
    for i, f in enumerate(files):
        for txt, sc, cx, cy in ocr_results.get(f, []):
            if not (px <= cx <= px + pw and py <= cy <= py + ph): continue
            if PROG_RE.search(txt): continue              # 进度行, 跳过
            if not re.search(r'[\u4e00-\u9fff]', txt): continue  # 无汉字
            if len(re.sub(r'[\W_]+', '', txt)) < 3: continue    # 太短, 噪声
            k = _miss_task_key(txt)
            if not k: continue
            if k in have: continue                        # 已在时间线, 跳过
            if k not in raw_hits:
                raw_hits[k] = {"samples": [], "first": i, "last": i, "count": 0}
            d = raw_hits[k]
            d["samples"].append(txt)
            d["first"] = min(d["first"], i)
            d["last"] = max(d["last"], i)
            d["count"] += 1

    # 3. 过滤: 出现次数 < min_count 的视为偶发噪声, 丢弃
    cands = [d for k, d in raw_hits.items() if d["count"] >= min_count]
    if not cands:
        print("\n[漏任务核查] 未发现候选漏任务(所有读到的任务名都已在时间线中)。", flush=True)
        return []

    # 3.5 编辑距离细合并: 粗键(数字骨架+汉字数)会把同一任务的不同错字分成多组,
    #     再用编辑距离把"试练/试炼/试冻1-6"这类合并成一条
    cands = _merge_by_editdist(cands)

    # 4. 排序(按首次出现时间)并输出
    def _t(idx):
        return filename_to_time(files[idx]) if idx < len(files) else "?"
    rows = []
    for d in sorted(cands, key=lambda x: x["first"]):
        canon = _pick_rep(d["samples"])
        # 清洗代表名里的面板分隔符残留, 列前3个不同的OCR原文样本(去重)
        canon = re.sub(r'[\|｜]', '', canon).strip()
        uniq_samples = [re.sub(r'[\|｜]', '', s).strip() for s in dict.fromkeys(d["samples"]) if re.sub(r'[\|｜]', '', s).strip()]
        rows.append({
            "任务名": canon,
            "ocr样本": " / ".join(uniq_samples[:3]),
            "首次": _t(d["first"]),
            "末次": _t(d["last"]),
            "次数": d["count"],
        })

    # 打印 + 写文件
    print("\n" + "=" * 70, flush=True)
    print("【漏任务候选核查】OCR读到了任务名、但未出现在最终时间线的候选:", flush=True)
    print("(这类任务多因'OCR没读到进度数字'被丢弃。请人工用下方时间点核对原视频)", flush=True)
    print("=" * 70, flush=True)
    md = [f"# 候选漏任务清单 — {name}\n",
          f"> 以下任务被OCR读到了任务名, 但未出现在《主线任务时间线》中。\n",
          f"> 多因\"OCR没读到进度数字\"被脚本的'只采信有进度帧'规则丢弃。\n",
          f"> 请人工用【首次/末次时间】跳转原视频核对, 确认后告知AI是否加入时间线。\n",
          f"> (出现次数 < {min_count} 的偶发噪声已自动过滤)\n",
          "| # | 任务名(代表) | 首次出现 | 末次出现 | OCR读到次数 | OCR原文样本(错字变体) |",
          "|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        print(f"  {i}. {r['任务名']}  首次={r['首次']} 末次={r['末次']} 次数={r['次数']}  样本=[{r['ocr样本']}]", flush=True)
        md.append(f"| {i} | {r['任务名']} | {r['首次']} | {r['末次']} | {r['次数']} | {r['ocr样本']} |")
    md_text = "\n".join(md) + "\n"
    mp = os.path.join(out_dir, f"候选漏任务清单_{name}.md")
    open(mp, "w", encoding="utf-8").write(md_text)
    print(f"\n候选漏任务清单已导出: {mp}", flush=True)
    print("=" * 70, flush=True)
    return rows

# ============ 面板确认(保险层): 回显坐标+列出面板内OCR文字,供AI/人工核对 ============
def confirm_panel(panel, files, ocr_results):
    """
    保险机制: 把 --panel 传进来的坐标回显, 并在采样帧上列出
    "落在这个矩形范围内的所有OCR文字", 让AI/人工一眼看出:
      - 坐标对不对(任务文字有没有出现在列表里)
      - 坐标偏没偏(任务文字在不在范围外)
    返回 True=确认无误可继续, False=坐标有问题需重传。
    """
    px, py, pw, ph = panel
    print("\n" + "=" * 60, flush=True)
    print("【面板确认 · 保险层】", flush=True)
    print("=" * 60, flush=True)
    print(f"传入面板坐标: x={px} y={py} w={pw} h={ph}", flush=True)
    print(f"  → 覆盖范围: 横[{px}~{px+pw}]  纵[{py}~{py+ph}]", flush=True)
    print(f"  → 矩形右下角: ({px+pw}, {py+ph})", flush=True)
    print("-" * 60, flush=True)

    # 取若干采样帧(前中后),列出每帧面板范围内的文字
    step = max(1, len(files) // 5)
    samples = files[::step][:5]
    all_has_task = False
    for f in samples:
        texts = ocr_results.get(f, [])
        inside = [(txt, sc, cx, cy) for txt, sc, cx, cy in texts
                  if px <= cx <= px + pw and py <= cy <= py + ph]
        print(f"\n  ▶ 帧 {f}:", flush=True)
        if not inside:
            print(f"    [警告] 面板范围内没有任何OCR文字!", flush=True)
            print(f"    可能原因: ①坐标偏了 ②该帧面板被遮挡 ③OCR没读到这帧", flush=True)
        else:
            for txt, sc, cx, cy in sorted(inside, key=lambda t: t[3]):
                tag = ""
                m = PROG_RE.search(txt)
                if m and not is_exp_bar(txt, int(m.group(1)), int(m.group(2))):
                    tag = "  ← 进度数字(好迹象)"; all_has_task = True
                elif any(k in txt for k in TASK_KW):
                    tag = "  ← 含任务词(好迹象)"; all_has_task = True
                print(f"    [{cx:5.0f},{cy:5.0f}] sc={sc:.2f}  {txt}{tag}", flush=True)

    print("\n" + "-" * 60, flush=True)
    if all_has_task:
        print("✅ 检测到面板范围内有进度数字/任务词 → 坐标大概率正确", flush=True)
    else:
        print("⚠️  面板范围内没看到任何进度数字或任务词 → 坐标可能偏了!", flush=True)
        print("   建议AI: 重新用云端视觉确认面板坐标, 或改用 --diagnose 看整图OCR", flush=True)
    print("=" * 60, flush=True)

    # 交互式确认(有终端输入时才问;非交互环境自动放行)
    if sys.stdin.isatty():
        try:
            ans = input("\n面板坐标确认无误? 回车=继续分析, 输入n=中止重传: ").strip().lower()
            if ans == "n":
                print("已中止。请重新确认面板坐标后再跑。", flush=True)
                return False
        except (EOFError, KeyboardInterrupt):
            pass
    else:
        print("(非交互环境, 自动继续。如坐标有误请检查上方输出)", flush=True)
    return True


# ============ 主流程 ============
def main():
    ap=argparse.ArgumentParser(description="通用游戏主线任务自动分析(AI自动化版)")
    ap.add_argument("input",help="视频路径(.mp4) 或 单张图片(.jpg/.png)")
    ap.add_argument("--fps",type=int,default=2,help="每秒抽帧数(默认2)")
    ap.add_argument("--out",default=None,help="输出目录(默认输入文件旁自动建)")
    ap.add_argument("--panel",default=None,help="手动指定面板 x,y,w,h(AI确认后传)")
    ap.add_argument("--scale",type=int,default=2,help="图片放大倍数(默认2,字体小/识别低可调3-4)")
    ap.add_argument("--diagnose",action="store_true",help="诊断模式:只抽帧+OCR+导出原始结果,不分析")
    ap.add_argument("--confirm",action="store_true",help="面板保险层:传入--panel后先回显坐标+面板内文字,确认对了再分析")
    ap.add_argument("--dry-panel",action="store_true",help="只做面板确认(回显坐标+面板内OCR),不往下分析。用于AI先核对坐标")
    ap.add_argument("--strict",action="store_true",help="严格模式:本地找不到面板时停下报告,不默默整图跑。用于'本地优先'流程")
    ap.add_argument("--reuse-ocr",default=None,help="复用已有OCR缓存文件(带坐标格式),跳过抽帧+OCR,直接分析。用于改逻辑后快速验证")
    ap.add_argument("--prog-y",default=None,help="经验条y范围 ymin,ymax(排除经验条噪声)。AI视觉定位时报告,不写死y528-550")
    ap.add_argument("--fix-typo",default=None,help="错字修正表文件(每行 错字=正字 或 re:正则=替换)。脚本源码不写死错字,由AI清洗时动态传入。默认不修正")
    ap.add_argument("--task-below",action="store_true",help="任务名在进度数字【下方】时启用(默认False=上方,兼容原行为)。某些游戏(如神器传说)面板布局是\"进度在上、任务名在下\"")
    ap.add_argument("--no-audit-missed",action="store_true",help="跳过漏任务候选核查(默认开启核查)。核查会在出表格后扫描OCR,列出'读到名但被过滤'的候选漏任务供人工核对")
    ap.add_argument("--audit-min-count",type=int,default=3,help="漏任务候选的最低OCR读到次数(默认3),低于此视为偶发噪声过滤掉")
    args=ap.parse_args()

    if not os.path.exists(args.input):
        print(f"错误: 文件不存在 -> {args.input}"); sys.exit(1)

    is_image = args.input.lower().endswith(('.jpg','.jpeg','.png','.bmp','.webp'))
    vname = os.path.splitext(os.path.basename(args.input))[0]
    out_root = args.out or os.path.join(os.path.dirname(args.input) or ".", f"output_{vname}")
    frame_dir = os.path.join(out_root, "frames")
    os.makedirs(out_root, exist_ok=True)

    print("="*60, flush=True)
    print(f"输入: {args.input}", flush=True)
    print(f"模式: {'图片' if is_image else '视频'} | 放大: {args.scale}x | 诊断: {args.diagnose}", flush=True)
    print(f"输出: {out_root}", flush=True)
    print("="*60, flush=True)

    # ---- 第1步 & 第2步: 获取帧 + OCR (或复用缓存) ----
    rawp = os.path.join(out_root, "ocr_raw.txt")
    if args.reuse_ocr:
        # 【复用OCR缓存】跳过抽帧+OCR, 直接从带坐标的OCR文本加载。
        # 支持两种格式: 本脚本导出的"文本(sc)@[cx,cy]" 或 旧版"文本(sc)"
        print(f"\n[复用OCR缓存] 加载: {args.reuse_ocr}", flush=True)
        if not os.path.exists(args.reuse_ocr):
            print(f"错误: 缓存文件不存在 -> {args.reuse_ocr}"); sys.exit(1)
        ocr_results, files = load_ocr_cache(args.reuse_ocr)
        files.sort(key=sort_key)
        print(f"  加载完成: {len(files)}帧", flush=True)
    else:
        # ---- 第1步: 获取帧(视频抽帧 / 图片直接复制) ----
        if is_image:
            import shutil
            fname = os.path.basename(args.input)
            shutil.copy(args.input, os.path.join(frame_dir, fname))
            files = [fname]
            print(f"[图片模式] 直接OCR单张: {fname}", flush=True)
        else:
            print("\n[1/6] 抽帧...", flush=True)
            files = extract_frames(args.input, frame_dir, args.fps)
            if not files: print("抽帧失败"); sys.exit(1)

        # ---- 第2步: OCR ----
        print(f"\n[2/6] PaddleOCR 整图识别 (放大{args.scale}x)...", flush=True)
        ocr_results = ocr_all_frames(frame_dir, files, scale=args.scale)

    # 导出原始OCR(带坐标格式, 与漏检修复兼容: 文本(sc)@[cx,cy])
    with open(rawp, "w", encoding="utf-8") as f:
        for fn in files:
            ts = ocr_results.get(fn, [])
            f.write(f"{fn}\t{' | '.join(f'{t[0]}({t[1]:.2f})@[{t[2]:.0f},{t[3]:.0f}]' for t in ts)}\n")
    print(f"  原始OCR已导出: {rawp}", flush=True)

    # ---- 诊断模式: 打印摘要后退出 ----
    if args.diagnose:
        print("\n" + "="*60, flush=True)
        print("【诊断模式】本地OCR识别结果摘要", flush=True)
        print("="*60, flush=True)
        show = files[:8] if len(files) > 8 else files
        for fn in show:
            ts = ocr_results.get(fn, [])
            print(f"\n--- {fn} (共{len(ts)}条文字) ---", flush=True)
            for t in sorted(ts, key=lambda x: x[3]):
                print(f"  [{t[2]:5.0f},{t[3]:5.0f}] sc={t[1]:.2f}  {t[0]}", flush=True)
        print(f"\n完整原始结果见: {rawp}", flush=True)
        print("\n>> 判断标准:", flush=True)
        print("   如果上面能看到任务文字(如'打开1个宝箱') -> 本地OCROK, 可继续完整分析", flush=True)
        print("   如果完全看不到任务文字 -> 本地OCR读不出该游戏字体, 需AI用云端视觉辅助", flush=True)
        print("="*60, flush=True)
        return

    # ---- 第3步: 定位面板 ----
    print("\n[3/6] 定位任务面板...", flush=True)
    if args.panel:
        panel = tuple(int(x) for x in args.panel.split(","))
        print(f"  手动指定: x={panel[0]} y={panel[1]} w={panel[2]} h={panel[3]}", flush=True)
        # 保险层: --confirm 或 --dry-panel 时, 先核对坐标对不对
        if args.confirm or args.dry_panel:
            ok = confirm_panel(panel, files, ocr_results)
            if not ok:
                return  # 坐标有问题, 中止
            if args.dry_panel:
                print("\n[--dry-panel] 仅做面板确认, 不往下分析。坐标OK可去掉此参数重跑。", flush=True)
                return
    else:
        panel = auto_detect_panel(files, ocr_results)
        if panel: print(f"  自动定位: x={panel[0]} y={panel[1]} w={panel[2]} h={panel[3]}", flush=True)
        elif args.strict:
            # 严格模式: 本地找不到面板就停下, 不默默整图跑(让AI决定是否进视觉兜底)
            print("\n" + "="*60, flush=True)
            print("【本地定位失败 · 严格模式】", flush=True)
            print("="*60, flush=True)
            print("脚本没能在画面中找到足够的进度数字(X/X)来定位任务面板。", flush=True)
            print("可能原因: ①这游戏没有常驻任务面板 ②PaddleOCR读不出进度数字 ③进度数字被当经验条排除了", flush=True)
            print("\n>> 接下来由AI决定:", flush=True)
            print("   - 方案A: AI用视觉看图,确定主线任务那一行的窄框坐标,用 --panel 传进来", flush=True)
            print("   - 方案B: 这游戏可能不适合本工具(无常驻面板),跟用户商量换策略", flush=True)
            print("="*60, flush=True)
            print("\n已停下,未做分析。ocr_raw.txt 已导出,可供AI读取核验。", flush=True)
            return
        else:
            panel=(0,0,99999,99999); print("  命中不足, 用整图", flush=True)

    # ---- 第4-5步: 提取+时间线 ----
    # 解析 --prog-y 经验条y范围(可选): 不传则用旧分母判据兜底
    exp_y=None
    if args.prog_y:
        parts=[int(x) for x in args.prog_y.split(",")]
        if len(parts)==2: exp_y=(parts[0],parts[1]); print(f"  经验条y范围: {exp_y}(坐标排除)")
    print("\n[4/6][5/6] 提取任务信息 & 还原时间线...", flush=True)
    if args.task_below: print(f"  任务名在进度【下方】模式(below=True)", flush=True)
    timeline = build_timeline(files, ocr_results, panel, args.fps, exp_y, below=args.task_below)

    # ---- 第6步: 输出 ----
    # OCR错字修正: 默认no-op(源码空表,保留原文可追溯)。
    # AI清洗时可 --fix-typo 传外部错字表, 脚本不写死任何游戏错字(保持通用)。
    extra_fix=None
    if args.fix_typo:
        if not os.path.exists(args.fix_typo):
            print(f"  [警告] 错字表文件不存在: {args.fix_typo}, 跳过修字", flush=True)
        else:
            extra_fix={}
            for ln in open(args.fix_typo,encoding='utf-8'):
                ln=ln.strip()
                if not ln or ln.startswith('#') or '=' not in ln: continue
                k,v=ln.split('=',1)
                extra_fix[k.strip()]=v.strip()
            print(f"  加载错字表: {len(extra_fix)}条 (来自 {args.fix_typo})", flush=True)
    for t in timeline:
        t["任务"] = fix_ocr_typos(t["任务"], extra_fix)
    print("\n[6/6] 生成表格...", flush=True)
    export(timeline, out_root, vname)

    # ---- 第7步: 漏任务候选核查(整理表格后, 供人工核对原视频) ----
    # 扫描OCR原始数据, 找出"OCR读到了任务名、但被规则过滤掉"的候选漏任务,
    # 列出精准首末时间+出现次数, 供人工用时间点核对原视频后决定是否补入时间线。
    # 设计依据《手册》第六节: 漏任务先查证OCR读到没有, 再由人工核对, 不自动加入。
    print("\n[7/7] 漏任务候选核查...", flush=True)
    if args.no_audit_missed:
        print("  已通过 --no-audit-missed 跳过漏任务核查。", flush=True)
    else:
        # 错字修正后再核查: 这样清洗后的任务名不会被判为"漏任务"
        audit_missed_tasks(ocr_results, files, panel, timeline, out_root, vname,
                           min_count=args.audit_min_count)
    print(f"\n完成! 结果在: {out_root}", flush=True)

if __name__=="__main__":
    main()

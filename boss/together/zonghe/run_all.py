# -*- coding: utf-8 -*-
"""
================================================================================
 run_all.py — 一键整合分析（任务1 + 任务2 → 一份总报告）
================================================================================
任务1 = ..\\GameVideoAnalyzer\\game_analyzer.py      → 游戏概述 / 核心循环图 / 机制 / UI
任务2 = ..\\分析视频工具\\游戏任务分析_含漏任务核查.py → 主线任务时间线 / 候选漏任务清单

核心设计（省时省磁盘）：
  - 抽帧只做一次（默认 2fps 一秒两帧，任务2命名 X分XX秒_第N帧.jpg），两个任务共用
  - 任务1 先跑（快，OCR 只采样 90 帧，约 3-6 分钟）
  - 任务2 后跑（慢，全帧 OCR 带坐标；30 分钟视频约 2-10 小时，建议挂着等）
  - 全部完成后自动汇总成一份《总报告_视频名.md》（两部分结果都能看到）

用法（推荐流程 · 视频进 boss\videos，报告出 reports）：
  1) 把视频放进 boss\videos\（总工具统一视频入口，文件名起好认的名字，如 跃动小子2.mp4）
  2) 一条命令（视频名可带可不带扩展名，不传 --out 时报告自动输出到 together\reports\视频名\）：
     python run_all.py "跃动小子2" --panel 60,498,140,44 --scale 3
  3) 也支持直接传视频完整路径（老用法完全兼容）：
     python run_all.py "D:\某目录\视频.mp4" --panel ... --out "某目录"

参数（与任务2保持一致）：
  视频名或路径         videos\ 里的文件名（可省略扩展名），或视频完整路径
  --panel x,y,w,h     任务面板坐标（新游戏第一次跑需人工/AI先定位；同款游戏可复用）
  --task-below        任务名在进度数字【下方】时启用（如神器传说"进度在上名在下"布局）
  --prog-y y1,y2      经验条 y 范围（排除经验条噪声，可选）
  --scale N           OCR 放大倍数（默认2；竖屏小字游戏用3，如神器传说）
  --fps N             抽帧率（默认2=一秒两帧）
  --audit-min-count N 漏任务候选最低出现次数（默认3）
  --out 目录          输出目录（默认 together\reports\视频名\）

产物结构（默认输出到 reports\视频名\）：
  输出目录/
  ├── frames/                     共用抽帧（X分XX秒_第N帧.jpg）
  ├── game_report_*.md + core_loop_*.png + report/   任务1结果
  ├── 主线任务时间线_视频名.md/.csv                   任务2结果
  ├── 候选漏任务清单_视频名.md                        任务2漏任务核查（若有）
  ├── ocr_raw.txt                 任务2原始OCR（带坐标，可复用重跑）
  ├── task1_run.log               任务1子进程日志（排错用）
  └── 总报告_视频名.md            ⭐ 最终汇总（第一部分=任务1，第二/三部分=任务2）
================================================================================
"""
import os, sys, time, glob, argparse, subprocess, importlib.util, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_ROOT = os.path.normpath(os.path.join(HERE, ".."))            # together 根目录
TASK1 = os.path.join(TOOL_ROOT, "GameVideoAnalyzer", "game_analyzer.py")
TASK2 = os.path.join(TOOL_ROOT, "分析视频工具", "游戏任务分析_含漏任务核查.py")
VIDEOS_DIR = os.path.normpath(os.path.join(TOOL_ROOT, "..", "videos"))  # ★ 统一视频入口：boss\videos（总工具级，两路工具共用）
REPORTS_DIR = os.path.join(TOOL_ROOT, "reports")                  # ★ 固定报告输出目录

VIDEO_EXTS = [".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm", ".m4v", ".ts"]

def resolve_video(user_input):
    """解析视频位置：路径存在直接用；否则去 videos\\ 按名字匹配（可省略扩展名；唯一包含匹配也可）。
    返回绝对路径，找不到返回 None。"""
    u = user_input.strip().strip('"').strip("'")
    if os.path.exists(u):
        return os.path.abspath(u)
    if not os.path.isdir(VIDEOS_DIR):
        return None
    base = os.path.basename(u)
    # 1) 精确文件名（含扩展名）
    cand = os.path.join(VIDEOS_DIR, base)
    if os.path.exists(cand):
        return os.path.abspath(cand)
    vids = [fn for fn in os.listdir(VIDEOS_DIR)
            if os.path.splitext(fn)[1].lower() in VIDEO_EXTS]
    stem = os.path.splitext(base)[0]
    # 2) 主名完全相等（省略扩展名）
    for fn in vids:
        if os.path.splitext(fn)[0] == stem:
            return os.path.abspath(os.path.join(VIDEOS_DIR, fn))
    # 3) 唯一包含匹配（用户只说了名字的一部分）
    hits = [fn for fn in vids if stem in os.path.splitext(fn)[0]]
    if len(hits) == 1:
        return os.path.abspath(os.path.join(VIDEOS_DIR, hits[0]))
    if len(hits) > 1:
        log(f"提示: videos\\ 里有多条匹配“{stem}”: {', '.join(hits)}，请用完整文件名")
    return None

def log(msg):
    print(msg, flush=True)

def main():
    ap = argparse.ArgumentParser(description="一键整合: 任务1(游戏整体分析) + 任务2(主线任务时间线) → 总报告")
    ap.add_argument("input", help=r"视频：boss\videos\ 里的文件名(可省略扩展名) 或 视频完整路径")
    ap.add_argument("--out", default=None, help=r"输出目录(默认 together\reports\视频名\)")
    ap.add_argument("--panel", default=None, help="任务面板 x,y,w,h (新游戏需先定位)")
    ap.add_argument("--prog-y", default=None, help="经验条y范围 y1,y2 (可选)")
    ap.add_argument("--scale", type=int, default=2, help="任务2 OCR放大倍数(默认2, 竖屏小字用3)")
    ap.add_argument("--fps", type=int, default=2, help="抽帧率(默认2=一秒两帧)")
    ap.add_argument("--task-below", action="store_true", help="任务名在进度下方时启用")
    ap.add_argument("--audit-min-count", type=int, default=3, help="漏任务候选最低出现次数")
    args = ap.parse_args()

    # ★ 视频解析：路径直接用；否则去固定 videos\ 目录按名字匹配
    video = resolve_video(args.input)
    if not video:
        avail = []
        if os.path.isdir(VIDEOS_DIR):
            avail = [fn for fn in os.listdir(VIDEOS_DIR)
                     if os.path.splitext(fn)[1].lower() in VIDEO_EXTS]
        log(f"错误: 找不到视频 -> {args.input}")
        log(f"      已在固定目录查找: {VIDEOS_DIR}")
        log(f"      (把视频放进该目录即可，或改传视频完整路径)")
        log(f"      videos\\ 里现有视频: {', '.join(avail) if avail else '(空)'}")
        sys.exit(1)
    for p, tag in [(TASK1, "任务1"), (TASK2, "任务2")]:
        if not os.path.exists(p):
            log(f"错误: {tag}脚本不存在 -> {p}"); sys.exit(1)

    vname = os.path.splitext(os.path.basename(video))[0]
    # ★ 默认输出到固定 reports\视频名\（--out 可覆盖）
    out_root = args.out or os.path.join(REPORTS_DIR, vname)
    frame_dir = os.path.join(out_root, "frames")
    os.makedirs(VIDEOS_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)
    os.makedirs(out_root, exist_ok=True)

    t_start = time.time()
    log("=" * 66)
    log(f"输入视频 : {video}")
    log(f"输出目录 : {out_root}")
    log(f"任务1    : {TASK1}")
    log(f"任务2    : {TASK2}")
    log(f"面板坐标 : {args.panel or '自动定位(未传--panel)'} | task-below={args.task_below} | scale={args.scale} | fps={args.fps}")
    log("=" * 66)

    # ---- 动态加载任务2模块（只用它的函数，不跑它的main，零修改）----
    spec = importlib.util.spec_from_file_location("task2", TASK2)
    t2 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(t2)

    # ================= 第0步：抽帧（一次，两任务共用）=================
    log(f"\n[0] 抽帧一次（{args.fps} fps 一秒两帧，任务1/任务2 共用）...")
    t0 = time.time()
    files = t2.extract_frames(video, frame_dir, fps=args.fps)
    if not files:
        log("抽帧失败"); sys.exit(1)
    log(f"    抽帧 {len(files)} 张，耗时 {time.time()-t0:.0f}s -> {frame_dir}")

    # ================= 任务1：游戏整体分析（复用抽帧）=================
    log("\n[任务1] 游戏概述/核心循环（game_analyzer.py，复用抽帧，较快）...")
    t1 = time.time()
    cmd = [sys.executable, TASK1, video, "--reuse-frames", frame_dir, "--out", out_root]
    r = subprocess.run(cmd, capture_output=True, text=True)
    sub_log = os.path.join(out_root, "task1_run.log")
    open(sub_log, "w", encoding="utf-8").write((r.stdout or "") + "\n---stderr---\n" + (r.stderr or ""))
    cands = sorted(glob.glob(os.path.join(out_root, "game_report_*.md")))
    report1 = cands[-1] if cands else None
    if r.returncode != 0 or not report1:
        log(f"    任务1失败(returncode={r.returncode})，详见 {sub_log}；继续任务2...")
    else:
        log(f"    任务1完成，耗时 {time.time()-t1:.0f}s -> {os.path.basename(report1)}")
    t1_dur = time.time() - t1

    # ================= 任务2：主线任务时间线（复用抽帧）=================
    log("\n[任务2] 主线任务时间线（全帧OCR带坐标，耗时较长请耐心/可挂后台）...")
    t2s = time.time()
    ocr_results = t2.ocr_all_frames(frame_dir, files, scale=args.scale)
    rawp = os.path.join(out_root, "ocr_raw.txt")
    with open(rawp, "w", encoding="utf-8") as f:
        for fn in files:
            ts = ocr_results.get(fn, [])
            f.write(f"{fn}\t{' | '.join(f'{t[0]}({t[1]:.2f})@[{t[2]:.0f},{t[3]:.0f}]' for t in ts)}\n")
    log(f"    OCR完成（{len(files)}帧），已导出 -> {rawp}")

    # 面板：优先用传入坐标，否则自动定位，再不行整图兜底
    if args.panel:
        panel = tuple(int(x) for x in args.panel.split(","))
        log(f"    使用传入面板: x={panel[0]} y={panel[1]} w={panel[2]} h={panel[3]}")
    else:
        panel = t2.auto_detect_panel(files, ocr_results)
        if panel:
            log(f"    自动定位面板: x={panel[0]} y={panel[1]} w={panel[2]} h={panel[3]}")
        else:
            panel = (0, 0, 99999, 99999)
            log("    自动定位失败，用整图兜底（结果可能偏噪，建议人工定位后传 --panel 重跑）")

    exp_y = None
    if args.prog_y:
        parts = [int(x) for x in args.prog_y.split(",")]
        if len(parts) == 2:
            exp_y = (parts[0], parts[1]); log(f"    经验条y范围: {exp_y}")

    log("    还原任务时间线...")
    timeline = t2.build_timeline(files, ocr_results, panel, args.fps, exp_y, below=args.task_below)
    t2.export(timeline, out_root, vname)
    tl_md = os.path.join(out_root, f"主线任务时间线_{vname}.md")
    log(f"    时间线完成（{len(timeline)}个任务）-> {os.path.basename(tl_md)}")

    log("    漏任务候选核查...")
    audit_md = os.path.join(out_root, f"候选漏任务清单_{vname}.md")
    try:
        t2.audit_missed_tasks(ocr_results, files, panel, timeline, out_root, vname,
                              min_count=args.audit_min_count)
    except Exception as e:
        log(f"    漏任务核查出错(不影响主结果): {e}")
    t2_dur = time.time() - t2s
    log(f"    任务2完成，耗时 {t2_dur:.0f}s")

    # ================= 第3步：汇总总报告 =================
    log("\n[3] 汇总总报告...")

    def body(md_path):
        """读md并去掉第1行H1标题（总报告里用统一的章节大标题）"""
        if not md_path or not os.path.exists(md_path):
            return None
        lines = open(md_path, encoding="utf-8").read().splitlines()
        if lines and lines[0].startswith("# "):
            lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
        return "\n".join(lines)

    b1, b2, b3 = body(report1), body(tl_md), body(audit_md)

    L = []
    L.append(f"# 游戏分析总报告 — {vname}\n")
    L.append(f"> 生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    L.append(f"> 视频来源：`{video}`")
    L.append(f"> 抽帧：一秒两帧（{args.fps} fps）共 {len(files)} 张 —— 任务1/任务2 **共用一次抽帧**")
    L.append(f"> 任务1耗时：{t1_dur:.0f}s · 任务2耗时：{t2_dur:.0f}s · 总耗时：{time.time()-t_start:.0f}s")
    L.append("")
    L.append("---\n")

    L.append("# 第一部分 游戏概述与核心循环（任务1 · 整体分析）\n")
    if b1:
        L.append(b1)
    else:
        L.append("（任务1未产出结果，请查看 `task1_run.log` 排错）")
    L.append("\n---\n")

    L.append("# 第二部分 主线任务时间线（任务2 · 任务明细）\n")
    if b2:
        L.append(b2)
    else:
        L.append("（任务2未产出结果）")
    L.append("\n---\n")

    if b3:
        L.append("# 第三部分 候选漏任务清单（任务2 · 人工核对用）\n")
        L.append(b3)
        L.append("\n---\n")

    L.append("# 附录 产物清单\n")
    L.append("| 文件 | 说明 |")
    L.append("|------|------|")
    if report1:
        L.append(f"| `{os.path.basename(report1)}` | 任务1完整报告（概述/核心循环/机制） |")
        pngs = sorted(glob.glob(os.path.join(out_root, "core_loop_*.png")))
        if pngs:
            L.append(f"| `{os.path.basename(pngs[-1])}` | 核心循环环形图 |")
    L.append(f"| `主线任务时间线_{vname}.md` / `.csv` | 任务2任务时间线 |")
    if os.path.exists(audit_md):
        L.append(f"| `候选漏任务清单_{vname}.md` | 漏任务候选（人工核对） |")
    L.append(f"| `frames/` | 共用抽帧（{len(files)}张） |")
    L.append(f"| `ocr_raw.txt` | 任务2原始OCR带坐标（可用任务2 --reuse-ocr 秒级重跑） |")
    L.append(f"| `report/ocr_results.json` | 任务1采样OCR结果 |")
    L.append("")

    out_md = os.path.join(out_root, f"总报告_{vname}.md")
    open(out_md, "w", encoding="utf-8").write("\n".join(L))

    log("\n" + "=" * 66)
    log(f"✅ 总报告 -> {out_md}")
    log(f"   总耗时 {time.time()-t_start:.0f}s = 抽帧 {t0 and (time.time()-t_start-t1_dur-t2_dur):.0f}s + 任务1 {t1_dur:.0f}s + 任务2 {t2_dur:.0f}s")
    log("=" * 66)

if __name__ == "__main__":
    main()

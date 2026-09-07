# -*- coding: utf-8 -*-
"""
merge_report.py — 总汇总脚本（boss 调度层）
==============================================================
把两路工具的最终报告合并成一份《游戏分析总报告》：

  第一~三部分：together 的 总报告_<视频名>.md
               （游戏概述/核心循环 + 主线任务时间线 + 候选漏任务清单）
  第四部分  ：unlock_tool 的 解锁时间线.md
               （系统/面板图标在什么时间点解锁 + 审计）
  附录      ：各工具详细产物位置索引

只读两边的最终 md 产物，不改两个工具的任何内部文件（松耦合、零风险）。

用法：
  python merge_report.py <名>                        # 视频名=游戏名=统一叫 <名>
  python merge_report.py <名> --video-name 视频名     # 两边名字不同时分别指定
  python merge_report.py <名> --game-name 游戏名
  python merge_report.py <名> --out "D:\某目录"       # 自定义输出（默认 boss\reports\<名>\）

查找位置（相对 boss 根）：
  together 报告：together\reports\<视频名>\总报告_<视频名>.md
  unlock 报告 ：unlock_tool\reports\<游戏名>\解锁时间线.md
                （找不到再退回 unlock_tool\games\<游戏名>\解锁时间线.md）
  输出        ：reports\<名>\游戏分析总报告_<名>.md

说明：
  - 任一路没跑完也不报错，对应章节标记"未产出"，方便先合并已完成的
  - 报告里引用的图片（如 core_loop_*.png、ev 证据图）会自动把相对路径
    改写成"从输出目录指向原图"的相对路径，保证合并后图片仍能显示
"""
import os, re, sys, argparse, datetime

HERE = os.path.dirname(os.path.abspath(__file__))          # boss 根
TOGETHER = os.path.join(HERE, "together")
UNLOCK = os.path.join(HERE, "unlock_tool")
OUT_DEFAULT = os.path.join(HERE, "reports")

def log(msg):
    print(msg, flush=True)

def body(md_path, src_dir, out_dir):
    """读 md：去掉首行 H1；把相对图片路径改写成从 out_dir 指向原图的相对路径。"""
    if not md_path or not os.path.exists(md_path):
        return None, None
    lines = open(md_path, encoding="utf-8", errors="replace").read().splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    while lines and not lines[0].strip():
        lines = lines[1:]
    txt = "\n".join(lines)

    def fix(m):
        alt, p = m.group(1), m.group(2).strip()
        if p.startswith(("http:", "https:", "data:")) or os.path.isabs(p):
            return m.group(0)
        target = os.path.normpath(os.path.join(src_dir, p))
        rel = os.path.relpath(target, out_dir).replace("\\", "/")
        return f"![{alt}]({rel})"

    txt = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", fix, txt)
    return txt, os.path.abspath(md_path)

def main():
    ap = argparse.ArgumentParser(description="合并 together + unlock_tool 两路报告为一份《游戏分析总报告》")
    ap.add_argument("name", help="统一名称（视频名=游戏名时只填这个）")
    ap.add_argument("--video-name", default=None, help="together 侧的视频名（默认同 name）")
    ap.add_argument("--game-name", default=None, help="unlock 侧的游戏名（默认同 name）")
    ap.add_argument("--out", default=None, help="输出目录（默认 boss\\reports\\<名>\\）")
    args = ap.parse_args()

    vname = args.video_name or args.name
    gname = args.game_name or args.name
    out_dir = args.out or os.path.join(OUT_DEFAULT, args.name)
    os.makedirs(out_dir, exist_ok=True)

    # ---- 定位两路报告 ----
    t_path = os.path.join(TOGETHER, "reports", vname, f"总报告_{vname}.md")
    u_path = os.path.join(UNLOCK, "reports", gname, "解锁时间线.md")
    if not os.path.exists(u_path):
        u_path = os.path.join(UNLOCK, "games", gname, "解锁时间线.md")

    t_body, t_src = body(t_path, os.path.dirname(t_path), out_dir)
    u_body, u_src = body(u_path, os.path.dirname(u_path), out_dir)

    if t_body is None and u_body is None:
        log(f"错误: 两路报告都没找到，无可合并。")
        log(f"  已找 together: {t_path}")
        log(f"  已找 unlock  : {u_path}")
        sys.exit(1)

    # ---- 组装 ----
    L = []
    L.append(f"# 游戏分析总报告 — {args.name}\n")
    L.append(f"> 生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    L.append(f"> 统一名称：{args.name}（together侧视频名：{vname} · unlock侧游戏名：{gname}）")
    L.append(f"> 数据来源：together（玩法概述/任务时间线/漏任务核查） + unlock_tool（系统解锁时间线）")
    L.append("")
    L.append("---\n")

    if t_body:
        L.append("# 第一至三部分 玩法分析与主线任务（together）\n")
        L.append(t_body)
        L.append("\n---\n")
    else:
        L.append("# 第一至三部分 玩法分析与主线任务（together）\n")
        L.append(f"（未产出：未找到 {t_path}。请先跑 together\zonghe\run_all.py，再重新合并。）")
        L.append("\n---\n")

    if u_body:
        L.append("# 第四部分 系统解锁时间线（unlock_tool）\n")
        L.append(u_body)
        L.append("\n---\n")
    else:
        L.append("# 第四部分 系统解锁时间线（unlock_tool）\n")
        L.append(f"（未产出：未找到 {u_path}。请按 unlock_tool\AI工作手册.md 完成标定→分析→终审→finalize 后重新合并。）")
        L.append("\n---\n")

    L.append("# 附录 各工具详细产物索引\n")
    L.append("| 内容 | 位置（相对 boss） |")
    L.append("|------|------------------|")
    if t_body:
        L.append(f"| together 完整总报告（含核心循环图） | `together\\reports\\{vname}\\` |")
    if u_body:
        L.append(f"| unlock 解锁时间线详细产物（证据图/审计/工作数据） | `unlock_tool\\games\\{gname}\\`（或 `unlock_tool\\reports\\{gname}\\`） |")
    L.append(f"| 本合并报告所在 | `reports\\{args.name}\\` |")
    L.append("")
    L.append("> 提示：第四部分引用的证据截图存放于 unlock_tool 的游戏目录下，合并时已把图片链接改写为相对本报告的可显示路径。")
    L.append("")

    out_md = os.path.join(out_dir, f"游戏分析总报告_{args.name}.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    log("=" * 66)
    log(f"✅ 合并完成 -> {out_md}")
    parts = []
    parts.append("together✅" if t_body else "together✗(未产出)")
    parts.append("unlock✅" if u_body else "unlock✗(未产出)")
    log(f"   来源状态: {' + '.join(parts)}")
    log("=" * 66)

if __name__ == "__main__":
    main()

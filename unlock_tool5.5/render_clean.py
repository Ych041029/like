# -*- coding: utf-8 -*-
"""干净版《解锁时间线.md》渲染器（游戏无关）
输入（均为流水线既有产物）：
  games/<游戏>/work/timeline.json             终审核验后的解锁事件
  games/<游戏>/work/flymenu/scan_result.json  flymenu_scan.py 的菜单打开区间
  games/<游戏>/flymenu_tpl/menu_content.json  每种菜单的文字内容（AI 目检后填写一次）
  games/<游戏>/icon_names.json                图标 id→中文名（可选）
  games/<游戏>/flymenu/观测说明.md            本视频的观测说明（AI 每视频填写，可选）
用法：python render_clean.py <游戏目录>
产出：games/<游戏>/解锁时间线.md 与 reports/<游戏>/解锁时间线.md（干净版）
"""
import sys, os, json, io
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import fmtt

def io_read(p):
    return io.open(p, encoding='utf-8').read()

gdir = sys.argv[1] if len(sys.argv) > 1 else "games/灵画师"
FPS = 2
wdir = os.path.join(gdir, "work")
cfg = json.load(open(os.path.join(gdir, "config.json"), encoding="utf-8"))
tl = json.load(open(os.path.join(wdir, "timeline.json"), encoding="utf-8"))

iname_p = os.path.join(gdir, "icon_names.json")
iname = json.load(open(iname_p, encoding="utf-8")) if os.path.exists(iname_p) else {}
mcont_p = os.path.join(gdir, "flymenu_tpl", "menu_content.json")
mcont = json.load(open(mcont_p, encoding="utf-8")) if os.path.exists(mcont_p) else {}

def disp(rid):
    return iname.get(rid.removeprefix("ACT_"), rid)

# ---- 一、解锁与登场时间线 ----
evs = sorted(tl["events"], key=lambda e: e["t"])
rows1 = []
for e in evs:
    nm = e.get("name") or iname.get(e["id"].removeprefix("ACT_"), e["id"])
    rows1.append(f"| {e['t_disp']} | {nm} |")
sec1 = ("| 时间 | 事件 |\n|---:|---|\n" + "\n".join(rows1)) if rows1 else "（无）"

# ---- 未解锁清单（读取 AI 终审的 icon_status.json，不再自行推断）----
# icon_status.json 由 AI 终审后写入，每图标一行：
#   {"id": "fuli", "status": "unlocked", "time": "01:52", "actual_frame": "chaozhi"}
#   {"id": "xianmeng", "status": "locked"}
# 渲染器不再用"框位有无事件"来推断解锁状态（滑轨系统下图标会跨框移动，
# 框位无事件≠图标未登场）。
rois = cfg.get("rois", {})
seen = {e["id"].removeprefix("ACT_") for e in evs}
ist_p = os.path.join(gdir, "icon_status.json")
ist = json.load(open(ist_p, encoding="utf-8")) if os.path.exists(ist_p) else {}
lock = []
for it in rois.get("activity", []) + rois.get("nav", []):
    iid = it["id"]
    st = ist.get(iid, {}).get("status", "")
    if st == "unlocked":
        continue  # 已解锁，不列入
    if iid not in seen and st != "unlocked":
        nm = iname.get(iid, iid)
        extra = ist.get(iid, {}).get("note", "")
        lock.append(f"{nm}（{extra}）" if extra else nm)
for s in (rois.get("cultivation") or {}).get("slots", []):
    if s["id"] not in seen:
        lock.append(iname.get(s["id"], s["id"]))

# ---- 未解锁集合（解锁警觉：未解锁图标不可点击出菜单）----
seen_ids = {e['id'].removeprefix('ACT_') for e in evs}
lock = [iname.get(it['id'], it['id'])
        for it in rois.get('activity', []) + rois.get('nav', [])
        + (rois.get('cultivation') or {}).get('slots', [])
        if it['id'] not in seen_ids]

# ---- 二、飞出菜单点击记录（按图标分组；组内多状态模板合并）----
scan = json.load(open(os.path.join(wdir, "flymenu", "scan_result.json"),
                      encoding="utf-8"))
opens = scan.get("opens", {})
groups = {}
for tname, runs in opens.items():
    grp = tname.split("_")[0]
    groups.setdefault(grp, []).extend((r["start"], r["end"]) for r in runs)

sec2_rows = []
n_open = 0
for grp in sorted(groups):
    rs = sorted(groups[grp])
    merged = []
    for a, b in rs:
        if merged and a - merged[-1][1] <= 3:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    n_open += len(merged)
    info = mcont.get(grp, {})
    icon = info.get("icon", grp)
    content = info.get("content", grp)
    pairs = "；".join(f"{a//2//60:02d}:{a/2%60:04.1f}~{b//2//60:02d}:{b/2%60:04.1f}：{content}"
                      for a, b in merged)
    locked = "（未解锁，全片无点击无菜单）" if icon.split("（")[0] in lock else ""
    sec2_rows.append(f"| {icon} | {pairs}{locked} |")
sec2 = ("| 图标 | 点击时间点：飞出菜单内的信息（文字） |\n|---|---|\n"
        + "\n".join(sec2_rows)) if sec2_rows else "（未检出）"

tail = scan.get("tail_open", [])

# ---- 观测说明（AI 每视频撰写，存在则嵌入）----
obs_p = os.path.join(gdir, "flymenu", "观测说明.md")
obs = io_read(obs_p) if os.path.exists(obs_p) else \
    "（本视频的观测说明待 AI 撰写：写入 games/<游戏>/flymenu/观测说明.md 后重跑本渲染器）"

DOC = f'''# 灵画师 · 解锁时间线

**视频**：{tl["video"]}｜分析精度 2fps（±0.5 秒）；遮挡期间的解锁取重见后第一干净帧
**结论**：解锁/登场 **{len(evs)} 项**；飞出菜单点击 **{n_open} 次**；未解锁 {len(lock)} 项

---

## 一、解锁与登场时间线

{sec1}

## 二、飞出菜单点击记录（按图标分组）

{sec2}

## 三、未解锁（全程）

{"、".join(lock) if lock else "无"}

---

## 四、观测说明

{obs}

---

## 附录

| 内容 | 位置 |
|---|---|
| 飞出菜单逐次明细与证据 | work/flymenu/飞出菜单清单.md、work/flymenu/*.png |
| 机器原始事件 / 终审核验事件 | work/timeline_raw.json / work/timeline.json |
| 漏检归因与校准记录 | AI工作手册 §9.9 |
'''

for p in (os.path.join(gdir, "解锁时间线.md"),
          os.path.join("reports", cfg.get("game", "unnamed"), "解锁时间线.md")):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(DOC)
    print("written:", p)

# -*- coding: utf-8 -*-
"""终审出报告：把 names.json 里的名称填进时间线，生成正式MD
用法：python finalize.py <游戏目录>        例：python finalize.py games\mad_knights
names.json 放在游戏目录下，格式 {"区域ID": "名称", ...}，缺的显示"待审"。
"""
import json, os, sys

gdir = sys.argv[1] if len(sys.argv) > 1 else "."
tl = json.load(open(os.path.join(gdir, "work", "timeline.json"), encoding="utf-8"))
cfg = json.load(open(os.path.join(gdir, "config.json"), encoding="utf-8"))
npath = os.path.join(gdir, "names.json")
names = json.load(open(npath, encoding="utf-8")) if os.path.exists(npath) else {}

def nm(e):
    v = names.get(e["id"], e["name"] or "待审")
    return v.get("name", "待审") if isinstance(v, dict) else v

def confirm_time(e):
    v = names.get(e["id"])
    return v.get("time") if isinstance(v, dict) else None


def disp(rid):
    """names.json 里的显示名（无则用 id 本身）"""
    v = names.get(rid)
    if isinstance(v, dict):
        return v.get("name") or rid
    return v if isinstance(v, str) and v else rid


def locked_disp(rid):
    """无事件区域的显示名：names.json 有条目则用之，否则默认 X（未解锁）"""
    return disp(rid) if rid in names else f"{rid}（未解锁）"

def way(e):
    return ("遮挡后首次可见（区间%s~%s）" % (e.get("gap_start", ""), e["t_disp"])
            if e["mode"] == "reveal" else "直接目击")

def tm(e, precise=True):
    return e.get("t_precise", e["t_disp"]) if precise else e["t_disp"]

events = sorted(tl["events"], key=lambda e: (e["t"], e["id"]))
L = [f"# {cfg['game']} · 解锁时间线\n",
     f"- 视频：{tl['video']}　|　抽帧 {tl['fps']}fps 共 {tl['frames']} 帧",
     "- 时间规则：遮挡期间的解锁取【重见后第一个干净帧】；带秒位小数的为30fps加密复扫值\n"]

# 一、礼包面板
# v2.3：identity=moved/repeat/transient 的事件为"老图标移位/重现/瞬态"伪事件，不进报告
band = [e for e in events if e["kind"] == "band"
        and e.get("identity") not in ("moved", "repeat", "transient")]
L += ["## 一、礼包面板新增/变化", "",
      "| 时刻 | 名称(待审) | 方式 |", "|---:|---|---|"]
for e in band:
    L.append(f"| {tm(e)} | {nm(e)} | {way(e)} |")
band_seen = {e["id"] for e in band}
for it in (cfg.get("rois") or {}).get("activity") or []:
    if ("ACT_" + it["id"]) not in band_seen:
        L.append(f"| — | {locked_disp(it['id'])} | 全程无变化 |")

# 二、副本面板
nav = [e for e in events if e["kind"] == "nav"]
L += ["## 二、副本面板状态变化", "",
      "| 时刻 | 图标(待审) | 变化幅度(ham/dS) | 方式 |", "|---:|---|---|---|"]
for e in nav:
    L.append(f"| {tm(e)} | {nm(e)} | {e['ham']}/{e['dsat']:+} | {way(e)} |")
nav_seen = {e["id"] for e in nav}
for it in (cfg.get("rois") or {}).get("nav") or []:
    if it["id"] not in nav_seen:
        L.append(f"| — | {locked_disp(it['id'])} | 未解锁 | 全程锁定 |")

# 三、养成系统面板（样式每游戏固定一种，见 config cultivation.style）
# 每个已登记槽位都必须出现一行：有事件=解锁行，无事件=未解锁行
cultf = [e for e in events if e["kind"] == "cultf"]
cultg = [e for e in events if e["kind"] == "cultg"]
cult_cfg = (cfg.get("rois") or {}).get("cultivation") or {}
slots_cfg = cult_cfg.get("slots") or []
if slots_cfg or cultf or cultg:
    style = cult_cfg.get("style") or ("firstfill" if cultf else "gray2color")
    first_map = {}
    for e in (cultf if style == "firstfill" else cultg):
        first_map.setdefault(e["id"], []).append(e)
    slot_ids = [s["id"] for s in slots_cfg] or sorted(first_map)
    L += ["## 三、养成系统面板", "",
          f"解锁样式：{'首次填入（空剪影→填入，换装/升级不记）' if style == 'firstfill' else '灰色锁定→彩色点亮（同副本面板）'}",
          "",
          "| 槽位 | 名称 | 解锁时刻(确认) | 机器候选 | 判定方式 |",
          "|---|---|---:|---|---|"]
    for rid in slot_ids:
        es = sorted(first_map.get(rid, []), key=lambda e: e["t"])
        if not es:
            L.append(f"| {rid} | {disp(rid) if rid in names else '—'} | 未解锁 | — | 全程锁定 |")
            continue
        fill = next((x for x in es if not x.get("init_transient")), None) or es[0]
        extras = sum(1 for x in es if x is not fill and not x.get("init_transient"))
        ct = confirm_time(fill)
        shown = ct or tm(fill)
        mark = "" if ct else "  *(候选)*"
        extra_note = f"（后续变化 +{extras} 不计）" if extras else ""
        L.append(f"| {rid} | {nm(fill)}{extra_note} | **{shown}**{mark} | {tm(fill)} | {way(fill)} |")

# 四、战斗时段
L += ["## 四、战斗时段（HUD隐藏，追踪自动挂起）"] + [f"- {a} ~ {b}" for a, b in tl["battle_sessions"]]
# 五、疑似弹窗时段
L += ["\n## 五、疑似弹窗时段"] + [f"- {a} ~ {b}" for a, b in tl["popup_sessions"]]
L.append("\n---\n*证据截图见 ev 文件夹；`待审`条目请对照证据图命名后回填 names.json 重跑本命令。*")

out = os.path.join(gdir, "解锁时间线.md")
open(out, "w", encoding="utf-8").write("\n".join(L))

# 终审备注（游戏目录下 review_notes.md，存在则自动拼接到报告尾部）
notes_p = os.path.join(gdir, "review_notes.md")
if os.path.exists(notes_p):
    with open(notes_p, encoding="utf-8") as nf:
        with open(out, "a", encoding="utf-8") as rf:
            rf.write("\n" + nf.read())
    print("附注: 已拼接 review_notes.md")
cult_ids = {e["id"] for e in cultf + cultg}
unique_ids = set(cult_ids) | {e["id"] for e in band + nav}
pending = sorted(i for i in unique_ids if not (names.get(i) or next(
    (e["name"] for e in events if e["id"] == i), "")))
print("saved:", out)
print("唯一区域数:", len(unique_ids), "| 待审:", len(pending), pending[:10])

# v2：出报告后强制"压线事件清单 + 首末对拍审计"（漏检兜底，见手册9.2/9.4）
try:
    from lock_audit import run_audit, borderline_events
    borderline_events(gdir)
    run_audit(gdir)
except Exception as _ex:
    print("[audit] 未能执行首末对拍审计：", _ex)

# v2.1：正式报告同时发布到工具根目录 reports\<游戏名>\（固定交付位置）
try:
    import shutil
    root = os.path.dirname(os.path.abspath(__file__))
    rdir = os.path.join(root, "reports", str(cfg.get("game", "unnamed")))
    os.makedirs(rdir, exist_ok=True)
    shutil.copyfile(out, os.path.join(rdir, "解锁时间线.md"))
    print("已发布:", os.path.join(rdir, "解锁时间线.md"))
except Exception as _ex:
    print("[reports] 发布失败（不影响游戏目录内的本地报告）：", _ex)

# -*- coding: utf-8 -*-
"""render_clean.py 修复：未解锁判定改为读取 AI 终审的 icon_status.json"""
import io

p = 'render_clean.py'
t = io.open(p, encoding='utf-8').read()

# 在未解锁清单构建前，先读取 AI 终审的图标状态表
old = '''# ---- 未解锁清单 ----
rois = cfg.get("rois", {})
seen = {e["id"].removeprefix("ACT_") for e in evs}
lock = []
for it in rois.get("activity", []) + rois.get("nav", []):
    if it["id"] not in seen:
        lock.append(iname.get(it["id"], it["id"]))
for s in (rois.get("cultivation") or {}).get("slots", []):
    if s["id"] not in seen:
        lock.append(iname.get(s["id"], s["id"]))'''

new = '''# ---- 未解锁清单（读取 AI 终审的 icon_status.json，不再自行推断）----
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
        lock.append(iname.get(s["id"], s["id"]))'''

if old in t:
    t = t.replace(old, new, 1)
    print("render_clean.py 未解锁逻辑已修复")
else:
    print("!! 未找到目标代码段")
io.open(p, 'w', encoding='utf-8').write(t)
print("render_clean.py 已更新")

# -*- coding: utf-8 -*-
"""补齐：§9.9 标题转正 + render_clean 加未解锁行 + flymenu_scan 组级合并"""
import io, os

# 1. §9.9 标题转正
p = 'AI工作手册.md'
t = io.open(p, encoding='utf-8').read()
old = '### 9.9 飞出菜单分析（v1 实验任务，2026-09-02，应人类需求新增）'
new = '### 9.9 飞出菜单分析（v2.5 起为标准流程第⑥步，2026-09-02 应人类需求新增；\n    详见 §2 第⑥步与 render_clean.py 渲染器）'
if old in t:
    t = t.replace(old, new, 1)
    print('§9.9 标题已转正')
else:
    print('!! §9.9 标题原文未匹配，人工检查')
io.open(p, 'w', encoding='utf-8').write(t)

# 2. render_clean.py 加"未解锁"行到飞出菜单表（图标解锁状态一目了然）
p2 = 'render_clean.py'
t2 = io.open(p2, encoding='utf-8').read()
old2 = '    sec2_rows.append(f"| {icon} | {pairs} |")'
new2 = '''    locked = "（未解锁，全片无点击无菜单）" if icon.split("（")[0] in lock else ""
    sec2_rows.append(f"| {icon} | {pairs}{locked} |")'''
if old2 in t2:
    t2 = t2.replace(old2, new2, 1)
    # lock 变量需在 sec2 循环前定义
    t2 = t2.replace(
        "# ---- 二、飞出菜单点击记录（按图标分组；组内多状态模板合并）----",
        "# ---- 未解锁集合（解锁警觉：未解锁图标不可点击出菜单）----\n"
        "seen_ids = {e['id'].removeprefix('ACT_') for e in evs}\n"
        "lock = [iname.get(it['id'], it['id'])\n"
        "        for it in rois.get('activity', []) + rois.get('nav', [])\n"
        "        + (rois.get('cultivation') or {}).get('slots', [])\n"
        "        if it['id'] not in seen_ids]\n\n"
        "# ---- 二、飞出菜单点击记录（按图标分组；组内多状态模板合并）----")
    print("render_clean.py 已加未解锁标注")
else:
    print("!! render_clean.py 未找到目标行")
io.open(p2, 'w', encoding='utf-8').write(t2)
print("render_clean.py 已更新")

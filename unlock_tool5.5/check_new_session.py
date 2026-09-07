# -*- coding: utf-8 -*-
"""检查新会话的产物状态"""
import os, json, io

G = os.path.join("games", "灵画师")
print("== games/灵画师 根目录 ==")
for x in sorted(os.listdir(G)):
    p = os.path.join(G, x)
    tag = "DIR " if os.path.isdir(p) else "FILE"
    sz = os.path.getsize(p) if os.path.isfile(p) else ""
    print(f"  [{tag}] {x} {sz}")

for sub in ["work", "work/flymenu", "flymenu_tpl", "flymenu"]:
    p = os.path.join(G, sub)
    if os.path.isdir(p):
        fs = sorted(os.listdir(p))
        print(f"== {sub}/ ({len(fs)}) ==")
        for x in fs[:25]:
            print("   ", x)
        if len(fs) > 25:
            print("    ...")

# 关键产物存在性
for p in ["games/灵画师/work/timeline.json",
          "games/灵画师/work/timeline_raw.json",
          "games/灵画师/work/flymenu/candidates.json",
          "games/灵画师/work/flymenu/scan_result.json",
          "games/灵画师/flymenu_tpl/menu_content.json",
          "games/灵画师/解锁时间线.md",
          "reports/灵画师/解锁时间线.md"]:
    print(("存在  " if os.path.exists(p) else "缺失  ") + p)

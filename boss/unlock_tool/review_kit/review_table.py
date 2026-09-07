# -*- coding: utf-8 -*-
"""把 timeline.json 压成按 id 分组的事件链总表（紧凑审阅用）"""
import json, os, sys

gdir = sys.argv[1] if len(sys.argv) > 1 else "."
tl = json.load(open(os.path.join(gdir, "work", "timeline.json"), encoding="utf-8"))

print("battle_sessions:", tl["battle_sessions"])
print("popup_sessions:", tl["popup_sessions"])
print()
by = {}
for e in tl["events"]:
    by.setdefault(e["id"], []).append(e)
for rid in sorted(by, key=lambda k: (-len(by[k]), k)):
    print(f"== {rid} ({len(by[rid])}) ==")
    line = []
    for e in by[rid]:
        fl = "F" if e.get("fill_like") else "."
        it = "I" if e.get("init_transient") else "."
        pr = e.get("t_precise", "")
        line.append(f"{e['t_disp']}{'/'+pr if pr else ''} {e['mode'][:3]} h{e['ham']} s{e['dsat']:+}{fl}{it} {os.path.basename(e['ev']) if e.get('ev') else '-'}")
    for i in range(0, len(line), 3):
        print("  " + " | ".join(line[i:i+3]))

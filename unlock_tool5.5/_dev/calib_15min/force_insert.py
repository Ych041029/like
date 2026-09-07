# -*- coding: utf-8 -*-
"""调试：找锚点 + 强制插入三件套"""
import io

p = 'AI工作手册.md'
t = io.open(p, encoding='utf-8').read()

# 找"均已纠正"的所有出现位置
import re
for m in re.finditer('均已纠正', t):
    i = m.start()
    print(f"位置 {i}: ...{t[max(0,i-30):i+30]}...")

# 找 §9.9.1 的末尾
i991 = t.find('9.9.1')
print(f"\n§9.9.1 标题位置: {i991}")
# 找下一个 ### 或 ## 的位置
next_sec = len(t)
for pat in ['\n### ', '\n## ']:
    j = t.find(pat, i991 + 10)
    if j >= 0 and j < next_sec:
        next_sec = j
print(f"下一节位置: {next_sec}")
print(f"§9.9.1 末尾 100 字: ...{t[next_sec-100:next_sec]}")

# 直接在 §9.9.1 末尾（下一节之前）插入三件套
trio = '''

**三件套硬规格（发现异常时的必做三步，不得跳过、不得降级）**：
1. **起疑**：strip_sample/逐秒条带（原生分辨率）——缩略图不够看就用原生分辨率
   逐秒条带排查，不许在缩略图上直接下结论；
2. **钉秒**：densify2 精确到 0.01 秒——拿不准的时刻必须钉秒，不许用
   2fps 粒度值凑合；
3. **取证**：证据裁图换原生分辨率——缩略图/缩放裁图不能作为终版证据，
   证据必须是"菜单确实在场"的那一帧的原生分辨率裁图。
本次修的三处漏检（13:38.5 与 13:46.5 被合并、14:39 被门控吞、14:56.5 被误判
为弹窗）全部靠这三步找回——下次换任何游戏，同一套流程照走。'''
t = t[:next_sec] + trio + t[next_sec:]
io.open(p, 'w', encoding='utf-8').write(t)
# 终验
t2 = io.open(p, encoding='utf-8').read()
print("\n终验: 三件套硬规格 =", '三件套硬规格' in t2, "| 钉秒 =", '钉秒' in t2)

# -*- coding: utf-8 -*-
"""把"滑轨归因三件套"写进手册作硬规格"""
import io

p = 'AI工作手册.md'
t = io.open(p, encoding='utf-8').read()

anchor = '均已纠正。'
if anchor not in t:
    print('!! 未找到锚点')
else:
    insert_at = t.index(anchor) + len(anchor)
    new_text = '''

**三件套硬规格（发现异常时的必做三步，不得跳过、不得降级）**：
1. **起疑**：strip_sample/逐秒条带（原生分辨率）——缩略图不够看就用原生分辨率
   逐秒条带排查，不许在缩略图上直接下结论；
2. **钉秒**：densify2 精确到 0.01 秒——拿不准的时刻必须钉秒，不许用
   2fps 粒度值凑合；
3. **取证**：证据裁图换原生分辨率——缩略图/缩放裁图不能作为终版证据，
   证据必须是"菜单确实在场"的那一帧的原生分辨率裁图。
本次修的三处漏检（13:38.5 与 13:46.5 被合并、14:39 被门控吞、14:56.5 被误判
为弹窗）全部靠这三步找回——下次换任何游戏，同一套流程照走。'''
    t = t[:insert_at] + new_text + t[insert_after:]
    io.open(p, 'w', encoding='utf-8').write(t)
    print("三件套硬规格已写入手册")
    # 验证
    t2 = io.open(p, encoding='utf-8').read()
    print("验证:", '三件套硬规格' in t2, '|', 'densify2 钉秒' in t2, '|', '原生分辨率' in t2)

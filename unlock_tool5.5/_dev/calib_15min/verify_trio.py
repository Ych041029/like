# -*- coding: utf-8 -*-
"""验证三件套是否已写入手册"""
import io

t = io.open('AI工作手册.md', encoding='utf-8').read()
for kw in ['三件套硬规格', '钉秒', '起疑', '原生分辨率', '不得跳过', '均已纠正']:
    print(f"  {kw}: {'✓' if kw in t else '✗'}")
i = t.find('三件套硬规格')
if i >= 0:
    print('\n上下文:')
    print(t[max(0,i-50):i+300])
else:
    print('\n!! 三件套硬规格未找到')

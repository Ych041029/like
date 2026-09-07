# 解锁时间线通用工具 v2

从游戏录屏自动产出"哪个面板图标在什么时间点解锁"的时间线报告。
流水线：**人工拖框标定（一次）→ 扔视频 → 自动分析 → AI/人工逐条证据核验 →
MD 正式报告（自动附漏检审计）**。

> **交给 AI 助手操作**：把本文件夹整个给新会话的 AI，并让它先读
> `AI工作手册.md` 按手册 SOP 执行即可（手册含完整判定规则、踩坑清单与
> 第 9 节 v2 复盘修订）。

## 目录结构
```
unlock_tool/
├── calibrate.py        # 标定器：程序内拖框（支持人工截图；兼容中文路径）
├── analyze.py          # 分析器：抽帧→场景门控(gate_roi可选)→双指标检测→证据截图
├── densify.py          # 局部30fps加密复扫（t=停稳时刻 / t_first=出现时刻）
├── finalize.py         # 出正式报告（自动拼接 review_notes.md + 自动跑审计）
├── lock_audit.py       # 首末对拍审计 + 压线事件清单（漏检兜底，可手动重跑）
├── check_env.py        # 环境自检（换电脑部署后先跑：缺什么一目了然）
├── sample_frame.py     # 小工具：按 mm:ss 抽任意时刻帧
├── ai_review.py        # 生成 AI 审阅包
├── review_kit/         # 复核辅助工具集（详见下方"证据复核工具"）
├── 开始分析.bat         # 菜单入口（人类可自助操作）
├── AI工作手册.md        # AI 操作 SOP（先读这个）
├── videos/             # 【约定】待分析视频放这里（选菜单2/3/4时只输文件名）
├── reports/            # 【约定】正式报告固定输出到 reports\<游戏名>\解锁时间线.md
└── games/<游戏名>/      # 每个游戏一个目录（可整体搬到任意盘/路径）
    ├── config.json     # 标定配置（含 gate_roi/anchors/audit_alias）
    ├── names.json      # 终审命名与确认时刻
    ├── review_notes.md # 终审备注（finalize 自动拼接到报告尾部）
    ├── 解锁时间线.md    # 最终交付物
    └── work/
        ├── timeline.json      # 终审后事件（AI 核验修剪版）
        ├── timeline_raw.json  # 机器原始事件（修剪前备份）
        ├── review/            # 对照表/图廊/扫描图/审计首末对照图
        └── ev/*.png           # 每个事件的前/后证据帧
```
标准样例：mad_knights 已随 2026-08-31 精简删除；其验收视频仍在此机器
`D:\ych\deepseek思路\8.5晚测试\疯狂骑士团1.mp4`，需要回归验证时重建
`games\mad_knights\` 重跑分析，对照手册第 8 节标准答案 + `_dev\parity_check.py`。
（实战样例"灵画师"的 games 目录、videos 副本与报告已于 2026-09-01 经人工确认
全部删除；其两轮复盘产出沉淀为 `AI工作手册.md` 的流程 ①A、陷阱第 7/8 条与
9.2/9.3/9.5/9.6 修订。）

## 使用步骤（推荐直接双击 `开始分析.bat` 走菜单）
0. **放视频**：把待分析的游戏录屏拷进 `videos\` 文件夹。
   之后菜单里选分析时**只输文件名**即可（输完整路径也可以，两种都认）。
1. **标定**（每个游戏一次）：
   ```
   python calibrate.py "D:\我的截图.png"          （推荐：人工暂停截图，原图勿带播放器控件）
   python calibrate.py "D:\某视频.mp4" 6:40       （或报时间点由工具抽帧）
   ```
   窗口依次提示**三类**区域：【礼包面板】→【副本面板】→【养成系统面板】。
   **每类可画任意多个框**（每框 ENTER 确认，如左右两块面板就画两框），ESC 进下一类。
   养成系统面板逐槽一框，并把样式（gray2color=灰锁变彩 / firstfill=空剪影首填）
   填入 config 的 cultivation.style——样式每游戏固定一种，由人工确认。
2. **分析**：
   ```
   python analyze.py "D:\某视频.mp4" "D:\游戏目录"
   ```
   主页带动画（挂机战斗/飘字）的游戏必须在 config 配 `gate_roi`
   （选一块只在主页出现且稳定的区域做场景门控，见手册 9.1）。
   最高精度加 `--fps 30`（慢约 15 倍，产物写 work_f30）。
3. **证据核验 + 终审**：AI 逐条对照 ev 证据图判定真伪并命名
   （规则见手册第 4 节），填 `names.json` 和 `review_notes.md`；
   修剪 timeline.json 时先备份为 timeline_raw.json。
4. **出正式报告**：
   ```
   python finalize.py "D:\游戏目录"
   ```
   生成 `解锁时间线.md` 并**自动发布到 `reports\<游戏名>\`**（固定交付位置），
   同时**自动附带**：压线事件清单 + 首末对拍审计
   （疑似漏检须目检 work/review/audit_start_vs_end.png 裁决）。

## v2 相对 v1 的变化（2026-08-28，灵画师复盘）
| 变化 | 说明 |
|---|---|
| **三类面板**（2026-08-31 四类；2026-09-01 起移除装备栏面板） | 礼包面板/副本面板/养成系统面板；养成样式每游戏固定一种（gray2color=灰锁变彩，同副本；firstfill=空剪影首填），写入 config 的 cultivation.style；报告章节同步重排（手册9.5） |
| 中文路径全兼容 | calibrate/analyze 读写、截图分辨率对齐均支持中文路径（imdecode/tofile + ffprobe） |
| 截图标定模式修复 | 原方式一必然崩溃的 UnboundLocalError 已修 |
| gate_roi 场景门控 | 主页带挂机动画的游戏必配（整帧哈希会大面积误判，详见手册 9.1） |
| densify 双口径 | 返回 t（停稳）与 t_first（出现）；报告一律用出现时刻；窗口起点即新状态时 t_first=None 提示重设（手册 9.3） |
| finalize 自动审计 | 出报告自动跑 lock_audit：压线事件清单 + 首末对拍，弱信号漏检兜底 |
| review_notes.md | 终审备注放游戏目录下，finalize 自动拼接到报告尾部 |
| review_kit/ | 复核工具集，见下 |

## 证据复核工具（review_kit/）
| 工具 | 用途 | 用法 |
|---|---|---|
| sheets.py | 事件前/后帧对照大图（批量目检） | `python sheets.py <游戏目录> 输出名 行高 --id 追踪区id` |
| gallery.py | 某追踪区全部事件后帧状态图廊（看图标集合变化） | `python gallery.py <游戏目录> 追踪区id [行高]` |
| strip_sample.py | 某ROI按时间抽样时间轴（逐秒看演变） | `python strip_sample.py <游戏目录> x,y,w,h 秒1,秒2,... [列数]` |
| review_table.py | timeline 压缩成按区分组的事件链总表 | `python review_table.py <游戏目录>` |
| lock_audit.py | 首末对拍审计 + 压线清单（finalize 自动调） | `python lock_audit.py <游戏目录>` |
| pick_tail_frames.py | 标定候选帧选取（视频尾部均匀抽帧） | `python pick_tail_frames.py <视频> <输出目录> [数量] [起占比] [止占比]` |
| render_boxes.py | 标定提案渲染器（三类框画到帧上供人工确认；--base2x 配网格底图；可用 only 只渲染单类） | `python render_boxes.py <帧图> <提案.json> <输出.png> [缩放] [--base2x] [only]` |
| grid_overlay.py | 20px 坐标网格尺（AI/人工精确读框坐标用） | `python grid_overlay.py <帧图> <输出.png> [缩放]` |

## 转发给同事（换电脑部署 · 推荐 AI 同步操作）
整个 `unlock_tool` 文件夹拷给同事，然后把文件夹交给 AI（新会话说：
"请阅读 unlock_tool\AI工作手册.md，按手册 SOP 执行"）。环境准备由 AI 自动完成：
1. AI 先跑 `python check_env.py` 自检；
2. 缺 opencv/numpy → `pip install opencv-python numpy`（装正式版，勿用 headless）；
3. 缺 ffmpeg → `winget install Gyan.FFmpeg`（或官网下包把 bin 加入 PATH）；
4. 自检全绿后按手册 SOP 分析 videos\ 里的视频，报告自动落 reports\。

人类只需参与：标定拖框、复核确认、报告验收（手册第 0 节职责边界）。
游戏视频各自自备；工具对盘符/目录无要求（中文路径已兼容）。

附：若目标机器**完全无网络且无 AI**、需要纯人工离线安装，需自备四件——
Python 3.10 / opencv-python / numpy / ffmpeg（装法三条命令同上）；
此前做过的 offline_installer 离线包已移出工具包，需要时可按该清单重建。

## 设计要点（对应验证期踩过的坑）
| 坑 | 对策 |
|---|---|
| 彩色游戏UI干扰找彩框 | 程序内 selectROI 拖框，坐标零误差 |
| 抽光效/红点/飘字假信号 | 变化须保持≥1.5s 才算数；养成类格位阈值加倍 |
| 战斗/弹窗覆盖期乱报 | 场景门控：主页带动画的游戏用 gate_roi 子区域比对（手册9.1） |
| 换色不变形的解锁会漏 | 哈希+饱和度双指标并列 |
| 小图标变色/锁徽章消失漏检 | 首末对拍审计 + 色相直方图指标（手册9.2，弱信号盲区） |
| 遮挡期内解锁只能给区间 | 重见后第一干净帧为准 + 局部 30fps 加密重扫 |
| 入场动画把"出现"记成"停稳" | densify 返回 t_first / t 双口径，报告用出现时刻（手册9.3） |
| 大内存占用 | 流式逐帧读取 |

## 可调参数（config.json）
- `gate_roi`: [x,y,w,h] 场景门控子区域（动画主页必配）
- `anchors`: {"main": ["0:05", ...]} 主页基准帧（加速且稳定聚类）
- `audit_alias`: 原始id→终审事件id 映射（审计判"有事件覆盖"用）
- `params.band_thH/band_thS/band_persist` 等灵敏度参数：数值越小越灵敏、
  误报越多，反正有终审兜底。

## 环境要求
ffmpeg 在 PATH；opencv-python（带 GUI 正式版，勿装 headless 顶替）。
注意：本机 PaddleOCR 要求 opencv≤4.6，当前装的是 4.11——跑 OCR 相关旧脚本前需临时切回。

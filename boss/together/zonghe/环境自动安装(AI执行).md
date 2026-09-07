# 环境自动安装（AI执行）— Python 3.10 / ffmpeg / 依赖库

> 你（AI）的任务：把工具运行环境装到**当前这台电脑**上，装完通过终验。
> 前提：你能执行命令。**若你无法执行命令**，跳过自动安装，直接把第四节手动教程发给用户照做。

---

## ⚠️ 路径基准声明

本文档所有相对路径基于 together 文件夹（下称"根"）。执行前先向用户确认根的实际位置，并把相对路径拼成绝对路径再执行。执行命令前先 `chcp 65001` 防中文乱码。

## 五条铁律（先读）

1. **先体检，缺什么装什么**，已合格的不重复装
2. **Python 只准装 3.10**（`Python.Python.3.10`），**禁止装最新版**——3.11+ 会导致 numpy<2 / paddlepaddle 装不上
3. **winget 装完后，你当前会话的 PATH 读不到新装的东西**（环境变量不回传给已运行进程）——这是正常现象，**验证和调用一律用固定绝对路径**（各步已给出）
4. **任何一步失败**（winget 不存在 / 无权限 / 网络被拦 / 安装报错）→ 立即停止自动安装，把第四节对应手动教程发给用户；用户装完回来喊你继续第五节终验
5. 电脑上已有**其他版本 Python 时不许卸载**（可能影响用户其他软件），用绝对路径或 `py -3.10` 调用 3.10

---

## 第一步：体检（判断缺什么）

```
python --version     ← 合格：3.8~3.10（"不是内部命令"或显示3.11+ = 不合格）
ffmpeg -version      ← 合格：显示版本号
python -c "import paddleocr, numpy, PIL, matplotlib; print('OK')"   ← 合格：显示OK
```

- 三项全合格 → 直接报告"环境已就绪"，结束本文档，进入《新会话AI使用说明.md》工作流
- 有不合格项 → 记下缺什么，按第二步对应小节逐项安装（装完统一做第五节终验）

---

## 第二步A：安装 Python 3.10（仅当 python 缺失或版本不在 3.8~3.10）

1. 检查 winget 可用性：
   ```
   winget --version
   ```
   报"不是内部命令" → 转第四节教程A（手动安装）
2. 安装（★锁死 3.10，勿改版本号）：
   ```
   winget install -e --id Python.Python.3.10 --accept-package-agreements --accept-source-agreements
   ```
   （来源为微软源里的 python.org 官方安装包；装完静默等待10秒）
3. **用绝对路径验证**（当前会话 PATH 没刷新是正常的，不要因此误判失败）：
   ```
   "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" --version
   ```
   该路径不存在时，依次再试：`C:\Program Files\Python310\python.exe`、`py -3.10 --version`
4. 验证通过后：
   - 本会话内调用 python **一律用上面验证通过的绝对路径**（下称 PY）
   - 告知用户：**重开终端/AI会话后** `python` 命令即全局可用

## 第二步B：安装 ffmpeg（仅当 ffmpeg 缺失）

**优先级1——用户已提供 ffmpeg 绿色文件夹**（含 ffmpeg.exe / ffprobe.exe 的压缩包或文件夹）：
1. 让用户解压到 `C:\ffmpeg`（解压后应存在 `C:\ffmpeg\bin\ffmpeg.exe`）
2. 加入用户 PATH（AI 执行，防重复追加）：
   ```
   powershell -Command "$p=[Environment]::GetEnvironmentVariable('Path','User'); if($p -notlike '*C:\ffmpeg\bin*'){[Environment]::SetEnvironmentVariable('Path', ($p.TrimEnd(';')+';C:\ffmpeg\bin'), 'User')}"
   ```
3. 验证（绝对路径）：`C:\ffmpeg\bin\ffmpeg.exe -version` 有输出即成功

**优先级2——没有绿色包，用 winget**：
```
winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
```
验证（绝对路径）：`"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe" -version` 有输出即成功（winget 装的便携版会自动放到 Links，重开终端即在 PATH 里）

失败 → 转第四节教程B。

## 第二步C：安装 Python 依赖库（仅当 import 检查不全）

用第一步确定的 PY（绝对路径）执行：
```
PY -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
PY -m pip install -r "根\zonghe\requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple
```
（`PY` 替换为第二步A验证通过的绝对路径；约5-15分钟）

也可以让用户双击 **根\zonghe\一键安装.bat**（等效，手动保底方式）。

验证：`PY -c "import paddleocr, numpy, PIL, matplotlib; print('OK')"`

---

## 第四节：失败兜底——手动教程（按需发给用户）

**教程A：手动装 Python 3.10**
1. 下载：https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe
2. 双击运行，第一屏底部 **务必勾选 "Add python.exe to PATH"**
3. 点 Install Now，装完**新开命令行**验证 `python --version` 显示 3.10.11

**教程B：手动装 ffmpeg**
- 有绿色包：解压到 `C:\ffmpeg` → 参照第二步B的 powershell 命令加 PATH（或：系统属性→环境变量→用户Path→新建 `C:\ffmpeg\bin`）→ 重开命令行验证
- 无绿色包：https://www.gyan.dev/ffmpeg/builds/ 下载 `ffmpeg-release-essentials.zip` → 解压改名为 `C:\ffmpeg` → 同上加 PATH → 重开命令行验证 `ffmpeg -version`

**教程C：手动装依赖库**：双击 `根\zonghe\一键安装.bat`，等最后 5 项全 OK

---

## 第五节：终验 + 完成汇报

重跑第一步的三项体检（python/ffmpeg 用绝对路径验证），**全部合格后**向用户汇报：

1. 环境就绪清单：Python 版本 ✅ / ffmpeg 版本 ✅ / 5 个依赖库 ✅
2. 提示：首次分析会自动下载 OCR 中文模型（约100MB，需联网，只下一次）
3. 提示：**重开终端/AI会话后 PATH 全局生效**；本会话内你已用绝对路径，不受影响
4. 结束语：环境就绪，之后进入《新会话AI使用说明.md》工作流——视频丢 `videos\`，说视频名即可分析

# -*- coding: utf-8 -*-
"""AI辅助终审：生成审阅包 或 调用视觉大模型自动命名
用法：
  模式A(无需API)  python ai_review.py <游戏目录>
      -> 生成 ai_review/ 文件夹：每个区域一张前后对比图 + prompt.txt
         把整包发给任何视觉大模型(或ZCode助手)，回填 names.json 后运行 finalize.py
  模式B(需API)    python ai_review.py <游戏目录> --api
      -> 自动调用 OpenAI 兼容视觉接口(GLM/通义等) 填写 names.json
      环境变量或 config.json->ai: {"api_key","base_url","model"}
"""
import cv2, os, sys, json, base64

def load(gdir):
    tl = json.load(open(os.path.join(gdir, "work", "timeline.json"), encoding="utf-8"))
    evd = os.path.join(gdir, "work", "ev")
    ids, firsts = [], {}
    for e in sorted(tl["events"], key=lambda x: (x["t"], x["id"])):
        rid = e["id"]
        if rid not in firsts and e.get("ev"):
            firsts[rid] = e
            ids.append(rid)
    return tl, evd, ids, firsts

def build_package(gdir, tl, evd, ids, firsts):
    out = os.path.join(gdir, "ai_review"); os.makedirs(out, exist_ok=True)
    rows = []
    for rid in ids:
        e = firsts[rid]
        b = cv2.imread(os.path.join(evd, os.path.basename(e["ev"]) + "_b.png"))
        a = cv2.imread(os.path.join(evd, os.path.basename(e["ev"]) + "_a.png"))
        if b is None or a is None: continue
        H = max(b.shape[0], a.shape[0])
        sep = np.full((H, 6, 3), 255, np.uint8)
        row = np.hstack([b, sep, a])
        bar = np.full((26, row.shape[1], 3), 30, np.uint8)
        cv2.putText(bar, f"{rid} @ {e['t_disp']}", (6, 19),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1, cv2.LINE_AA)
        cv2.imwrite(os.path.join(out, f"{rid}.png"), np.vstack([bar, row]))
        rows.append(f"- 区域ID {rid}，事件时间 {e['t_disp']}，对比图 {rid}.png")
    prompt = (
        "你是游戏UI识别助手。下面是某游戏录屏的自动检测结果：每个区域ID对应一张"
        "【变化前|变化后】对比图。请你：\n"
        "1) 识别该区域是什么（图标名/面板名），中文填写 name；\n"
        "2) 判断这是否为真实解锁/填入，排除纯动画、光效、红点干扰（若为噪声，"
        "name 填 噪声）；\n"
        "3) 如需修正时刻可填 time，否则省略；\n"
        "4) 只输出一个 JSON 对象，键为区域ID，格式：\n"
        '{"区域ID": {"name":"...","time":"mm:ss.xx(可选)","note":"一句话理由"}}\n\n'
        "区域清单：\n" + "\n".join(rows) + "\n")
    open(os.path.join(out, "prompt.txt"), "w", encoding="utf-8").write(prompt)
    print(f"[package] {len(rows)}个区域 -> {out}\\  (含 prompt.txt)")
    return out, prompt

import numpy as np  # noqa: E402

def call_api(gdir, cfg, prompt, ids, firsts, evd):
    ai = cfg.get("ai") or {}
    key = ai.get("api_key") or os.environ.get("AI_API_KEY")
    base = ai.get("base_url", "https://open.bigmodel.cn/api/paas/v4")
    model = ai.get("model", "glm-4v-plus")
    if not key:
        print("[api] 未配置 api_key（config.json->ai 或环境变量 AI_API_KEY），改用模式A")
        return None
    import urllib.request
    content = [{"type": "text", "text": prompt[:3000]}]
    for rid in ids[:20]:
        p = os.path.join(evd, os.path.basename(firsts[rid]["ev"]) + "_a.png")
        if os.path.exists(p):
            b64 = base64.b64encode(open(p, "rb").read()).decode()
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"}})
    body = json.dumps({"model": model,
                       "messages": [{"role": "user", "content": content}]}).encode()
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    resp = json.loads(urllib.request.urlopen(req, timeout=120).read())
    text = resp["choices"][0]["message"]["content"]
    s, e_ = text.find("{"), text.rfind("}")
    names = json.loads(text[s:e_+1]) if s >= 0 else {}
    np_ = os.path.join(gdir, "names.json")
    old = json.load(open(np_, encoding="utf-8")) if os.path.exists(np_) else {}
    for k, v in names.items():
        old[k] = v if isinstance(v, dict) else {"name": str(v)}
    json.dump(old, open(np_, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[api] 已写入 {len(names)} 个名称 -> names.json")

def main():
    gdir = sys.argv[1]
    tl, evd, ids, firsts = load(gdir)
    cfg = json.load(open(os.path.join(gdir, "config.json"), encoding="utf-8"))
    if "--api" in sys.argv:
        out, prompt = build_package(gdir, tl, evd, ids, firsts)
        call_api(gdir, cfg, prompt, ids, firsts, evd)
    else:
        build_package(gdir, tl, evd, ids, firsts)
        print("[next] 把 ai_review 文件夹发给AI -> 得到JSON -> 存为 names.json -> "
              "python finalize.py", gdir)

if __name__ == "__main__":
    main()

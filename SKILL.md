---
name: bili-transcript
description: 提取 B 站（bilibili）视频的口播文案/字幕。当用户给出 BV 号或 B 站视频链接并想要「视频文案、口播稿、字幕、逐字稿、讲了什么」时使用。字幕优先，无字幕则下载音频本地 Whisper 转写，产出带时间轴的中文文案。
---

# B 站视频文案提取

## 决策流程

1. **先查有没有现成字幕**（成本最低）
   `scripts/bili_transcript.py BV号` 会自动走这一步。若 `subtitle` 列表非空，直接下载官方/AI 字幕，无需转写。
2. **没字幕 → 音频转写**。B 站很多搬运投稿（如视频号 mmexport 上传）既无 CC 字幕也无 AI 字幕，只能走 ASR。
3. **AI 总结接口不可行**：`/x/web-interface/view/conclusion/get` 未登录返回 `-403 访问权限不足`，别浪费时间。

## 安装（首次）

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

需要 Python 3.10+。faster-whisper 依赖 `av` 自带解码能力，**无需系统 ffmpeg**。

## 执行

```bash
HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1 \
python scripts/bili_transcript.py BV1xxxxxxxxx \
  --outdir "./out" --prompt "以下是普通话的中文口播内容，关于……"
```

- Whisper 模型首次运行会自动下载（`small` 约 464MB），缓存到 `~/.cache/whisper_models_cache`；可用环境变量 `WHISPER_CACHE` 指定其他目录。**不要下载到项目目录**。
- `small` 模型 + int8 + CPU：4 分钟音频约 110 秒。追求更快用 `base`，更准用 `medium`。
- 未登录下载最高 480P；只取音频轨（30280）足够转写。
- **模型缓存有两层嵌套，`download_root` 容易命中不了而联网**：huggingface_hub 实际把仓库放在
  `<cache>/faster-whisper-small/models--Systran--faster-whisper-small/snapshots/<rev>`。
  所以直接 `WhisperModel("small", download_root=...)` 可能走网络，国内代理常返回
  `httpx.ProxyError: 502 Bad Gateway`。
  **解法：把 snapshot 目录当 `model_size_or_path` 直接传给 `WhisperModel`**（脚本的 `resolve_model_path()` 已自动做这件事），faster-whisper 见到本地目录就不再联网。若缓存为空，才需要联网下载（届时设 `HF_ENDPOINT` + `HF_HUB_DISABLE_XET`）。
- **Windows PowerShell 抓 Python 输出会乱码/不回显**：用 `*>&1 | Out-File -Encoding utf8 xxx.log` 落盘再读，别指望终端直接显示。

## 关键坑（都踩过）

- **HF 下载 401**：huggingface xet 后端在国内走 `cas-server.xethub.hf.co` 报 `401 Unauthorized`。
  必须 `HF_ENDPOINT=https://hf-mirror.com` + `HF_HUB_DISABLE_XET=1`，两个都要设（脚本内已设，命令行再设一次更稳）。
- **B 站接口要 wbi 签名**：`/x/player/wbi/v2`、`/x/player/wbi/playurl` 需要 wbi（mixin key 算法见脚本）。
  先用 `x/frontend/finger/spi` 初始化 buvid3 cookie，否则返回 -352。
- **av 解码后 ndarray 拼接**：frame 是 shape `(1, N)`，必须 `reshape(-1)` 再 `np.concatenate`，否则报 dimension mismatch。
- **m4s 下载**：请求头必须带 `Referer: https://www.bilibili.com/`。
- **ASR 同音错字必须人工校正**：中文口播常见如「投言→投研」「假尴尬→加杠杆」「库承和→护城河」「议论表→利润表」「律师→历史」。
  交付时按上下文校正，并在文件里附一份未校正原文备查。

## 交付格式

Markdown 文件，包含：
1. 元信息表（标题/UP主/时长/BV号/播放数据/简介）
2. 校正后的分段文案（按主题分节，附时间轴）
3. 核心框架速览表（若视频是方法论类）
4. 附录：未校正原始转写（带时间轴）

## 其他可用接口

- 视频信息：`https://api.bilibili.com/x/web-interface/view?bvid=xxx`（拿 aid/cid/时长/UP主/统计）
- 字幕轨：`https://api.bilibili.com/x/player/wbi/v2?aid=&cid=`（wbi 签名）
- 音视频流：`https://api.bilibili.com/x/player/wbi/playurl?bvid=&cid=&fnval=16`（wbi 签名）

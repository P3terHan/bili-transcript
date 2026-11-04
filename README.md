# bili-transcript

> 从 B 站视频提取口播文案 / 字幕。**字幕优先，无字幕则本地 Whisper 转写**，产出带时间轴的中文逐字稿。

一个零依赖冲突的小工具：不用系统 ffmpeg、不用 yt-dlp，直接调 B 站 web 接口拿字幕；拿不到就把音轨下下来，用 [faster-whisper](https://github.com/SYSTRAN/faster-whisper) 在本地 CPU 转写。

## 特性

- **字幕优先**：有官方 / AI 字幕就直接下，0 转写成本、最准。
- **无字幕兜底**：自动取最高码率音轨 → 本地 Whisper（int8/CPU）转写，带 `[起-止]` 时间轴。
- **免系统依赖**：只用 `faster-whisper + av`，`av` 自带解码，Windows 上不用装 ffmpeg。
- **B 站接口签名**：内置 wbi mixed-key 算法与 buvid3 初始化，绕开 `-352`。
- **可作 DSH / WorkBuddy Skill 使用**：保留 `SKILL.md` 说明，交给 Agent 自动按流程调用。

## 安装

```bash
git clone https://github.com/P3terHan/bili-transcript.git
cd bili-transcript
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

需要 Python 3.10+。首次运行会自动下载 Whisper `small` 模型（约 464MB）到 `~/.cache/whisper_models_cache`；可用环境变量 `WHISPER_CACHE` 指定目录。

## 安装为 Skill（DSH / WorkBuddy）

本仓库本身就是一个 skill（根目录 `SKILL.md` + `scripts/`）。克隆进对应产品的 skills 目录即可被扫描到：

```powershell
# DSH（默认目录 ~/.dsh/skills）
git clone https://github.com/P3terHan/bili-transcript.git "$env:USERPROFILE\.dsh\skills\bili-transcript"

# WorkBuddy（默认目录 ~/.workbuddy/skills）
git clone https://github.com/P3terHan/bili-transcript.git "$env:USERPROFILE\.workbuddy\skills\bili-transcript"
```

依赖不随仓库携带，装完后安装依赖并**重启该产品**，skill 才会被重新扫描加载：

```powershell
cd "$env:USERPROFILE\.dsh\skills\bili-transcript"
python -m venv .venv; .\.venv\Scripts\activate; pip install -r requirements.txt
```

### 给 Agent 的一句话提示词

> 把 https://github.com/P3terHan/bili-transcript 克隆到本产品的 skills 目录（DSH 为 `~/.dsh/skills/bili-transcript`，WorkBuddy 为 `~/.workbuddy/skills/bili-transcript`），安装 `requirements.txt` 依赖后重启；以后收到 BV 号就用该 skill 提取文案。

> ⚠️ 两个硬限制：① skill 在**启动时**扫描，装完必须重启才能被调用；② 仓库不带 Python 依赖，需自行 `pip install -r requirements.txt`，Whisper 模型首次运行才会下载。

## 使用

```bash
# 有字幕：直接抓字幕
python scripts/bili_transcript.py BV1xxxxxxxxx --outdir ./out

# 无字幕：自动转写（可加 --prompt 提示领域，提升同音字准确率）
HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1 \
python scripts/bili_transcript.py BV1xxxxxxxxx --outdir ./out \
  --prompt "以下是普通话的中文口播内容，关于……"

# 只要字幕，不要转写
python scripts/bili_transcript.py BV1xxxxxxxxx --no-asr
```

参数：`--outdir` 输出目录、`--model`（`base`/`small`/`medium`，默认 `small`）、`--prompt` 领域提示、`--no-asr` 禁用转写。

## 输出

- 有字幕：`subtitle_<lang>.txt`，每行 `[起始秒] 文本`
- 无字幕：`transcript.txt`，每行 `[起-止] 文本`（临时 `audio.m4s` 转写后自动删除）

## 工作原理

```
BV号 → 初始化 buvid3 + wbi key
     → /x/web-interface/view            取 title/UP/aid/cid
     → /x/player/wbi/v2                 查字幕轨
         ├─ 有 → 下载 subtitle_url → txt
         └─ 无 → /x/player/wbi/playurl  取音轨
                 → 下 m4s → faster-whisper 转写 → transcript.txt
```

## 限制

- 仅支持 B 站（BV 号）。
- 未登录最高 480P，但只取音频轨，足够转写。
- CPU 转写：`small` 约 110 秒 / 4 分钟音频；长视频请分段处理。
- ASR 存在同音错字，交付前建议人工按上下文校正。

## 免责声明

本项目仅用于个人学习研究，请遵守 B 站用户协议，详见 [DISCLAIMER.md](./DISCLAIMER.md)。

## License

[MIT](./LICENSE) © 2026 P3terHan

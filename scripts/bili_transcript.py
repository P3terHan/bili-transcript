"""
B 站视频口播稿提取：BV号 -> 字幕优先，无字幕则下载音频 -> 本地 Whisper 转写。

用法:
  python bili_transcript.py BV1ECtA62Eso [--outdir DIR] [--model small] [--no-asr]

依赖:
  pip install -r requirements.txt   (faster-whisper + av)

模型缓存目录: ~/.cache/whisper_models_cache（可用环境变量 WHISPER_CACHE 覆盖）
运行时需设置: HF_ENDPOINT=https://hf-mirror.com  HF_HUB_DISABLE_XET=1
"""
import os, sys, json, time, re, hashlib, argparse, urllib.parse, urllib.request, http.cookiejar

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
MODEL_CACHE = os.environ.get("WHISPER_CACHE") or os.path.join(
    os.path.expanduser("~"), ".cache", "whisper_models_cache")
MIXIN = [46,47,18,2,53,8,23,32,15,50,10,31,58,3,45,35,27,43,5,49,33,9,42,19,29,28,14,39,12,38,41,13,37,48,7,16,24,55,40,61,26,17,0,1,60,51,30,4,22,25,54,21,56,59,6,63,57,62,11,36,20,34,44,52]


class Bili:
    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self.op.addheaders = [("User-Agent", UA), ("Referer", "https://www.bilibili.com/")]
        self.get("https://www.bilibili.com/")
        self.get("https://api.bilibili.com/x/frontend/finger/spi")
        nav = json.loads(self.get("https://api.bilibili.com/x/web-interface/nav"))["data"]["wbi_img"]
        a = nav["img_url"].rsplit("/", 1)[1].split(".")[0]
        b = nav["sub_url"].rsplit("/", 1)[1].split(".")[0]
        self.mk = "".join((a + b)[i] for i in MIXIN)[:32]

    def get(self, url, headers=None):
        req = urllib.request.Request(url, headers=headers or {})
        return self.op.open(req, timeout=30).read().decode("utf-8", "ignore")

    def getbin(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Referer": "https://www.bilibili.com/",
                                                   "Range": "bytes=0-"})
        return self.op.open(req, timeout=180).read()

    def wbi(self, p):
        p = dict(p)
        p["wts"] = int(time.time())
        q = re.sub(r"[!'\(\)*]", "", urllib.parse.urlencode(sorted(p.items())))
        p["w_rid"] = hashlib.md5((q + self.mk).encode()).hexdigest()
        return p

    def view(self, bvid):
        d = json.loads(self.get("https://api.bilibili.com/x/web-interface/view?bvid=" + bvid))
        if d.get("code") != 0:
            raise RuntimeError("view failed: %s" % d.get("message"))
        return d["data"]

    def subtitle_tracks(self, aid, cid):
        u = "https://api.bilibili.com/x/player/wbi/v2?" + urllib.parse.urlencode(self.wbi({"aid": aid, "cid": cid}))
        d = json.loads(self.get(u))
        sub = d.get("data", {}).get("subtitle", {})
        out = []
        for s in sub.get("subtitles", []) or sub.get("list", []):
            if s.get("subtitle_url"):
                out.append(s)
        for s in (sub.get("ai_subtitle") or {}).get("list", []):
            if s.get("subtitle_url"):
                out.append(s)
        return out

    def fetch_subtitle(self, track):
        u = track["subtitle_url"]
        if u.startswith("//"):
            u = "https:" + u
        j = json.loads(self.get(u))
        return [(b.get("from", i), b.get("content", "")) for i, b in enumerate(j.get("body", []))]

    def audio_url(self, bvid, cid):
        u = "https://api.bilibili.com/x/player/wbi/playurl?" + urllib.parse.urlencode(
            self.wbi({"bvid": bvid, "cid": cid, "fnval": 16, "qn": 0, "fourk": 1, "voice_balance": 1}))
        d = json.loads(self.get(u))
        if d.get("code") != 0:
            raise RuntimeError("playurl failed: %s" % d.get("message"))
        aud = sorted(d["data"]["dash"]["audio"], key=lambda x: x["id"], reverse=True)[0]
        return aud["baseUrl"] or aud["base_url"]


def resolve_model_path(model_size):
    """优先命中本地 snapshot 目录，避免 download_root 不生效导致联网 502。

    HF 缓存实际结构: <cache>/faster-whisper-<size>/models--Systran--faster-whisper-<size>/snapshots/<rev>
    faster-whisper 收到本地目录路径就不再联网。
    """
    if os.path.isdir(model_size):
        return model_size
    base = os.path.join(MODEL_CACHE, "faster-whisper-%s" % model_size,
                        "models--Systran--faster-whisper-%s" % model_size, "snapshots")
    if os.path.isdir(base):
        revs = sorted(os.listdir(base))
        if revs:
            return os.path.join(base, revs[-1])
    return model_size


def asr(audio_path, model_size="small", prompt=""):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    import av, numpy as np
    from faster_whisper import WhisperModel

    container = av.open(audio_path)
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    chunks = []
    for frame in container.decode(container.streams.audio[0]):
        for f in resampler.resample(frame):
            chunks.append(f.to_ndarray())
    for f in resampler.resample(None):
        chunks.append(f.to_ndarray())
    pcm = np.concatenate([c.reshape(-1) for c in chunks]).astype(np.float32) / 32768.0
    print("audio seconds: %.1f" % (len(pcm) / 16000), flush=True)

    model = WhisperModel(resolve_model_path(model_size), device="cpu", compute_type="int8",
                         download_root=MODEL_CACHE)
    segs, _ = model.transcribe(pcm, language="zh", beam_size=5, vad_filter=True,
                               vad_parameters=dict(min_silence_duration_ms=400),
                               initial_prompt=prompt or "以下是普通话的中文视频口播内容。")
    return [(s.start, s.end, s.text.strip()) for s in segs]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bvid")
    ap.add_argument("--outdir", default=os.getcwd())
    ap.add_argument("--model", default="small")
    ap.add_argument("--prompt", default="")
    ap.add_argument("--no-asr", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    b = Bili()
    info = b.view(args.bvid)
    aid, cid = info["aid"], info["cid"]
    print("title:", info["title"])
    print("up:", info["owner"]["name"], "| duration:", info["duration"], "s")

    tracks = b.subtitle_tracks(aid, cid)
    if tracks:
        print("found %d subtitle track(s)" % len(tracks))
        for t in tracks:
            lines = b.fetch_subtitle(t)
            p = os.path.join(args.outdir, "subtitle_%s.txt" % (t.get("lan") or "x"))
            open(p, "w", encoding="utf-8").write("\n".join("[%.1f] %s" % (x[0], x[1]) for x in lines))
            print("saved", p, len(lines), "lines")
        return

    print("no subtitle -> fallback ASR")
    if args.no_asr:
        return
    url = b.audio_url(args.bvid, cid)
    m4s = os.path.join(args.outdir, "audio.m4s")
    open(m4s, "wb").write(b.getbin(url))
    print("audio downloaded:", os.path.getsize(m4s), "bytes")

    segs = asr(m4s, args.model, args.prompt)
    out = os.path.join(args.outdir, "transcript.txt")
    with open(out, "w", encoding="utf-8") as f:
        for st, en, tx in segs:
            f.write("[%.1f-%.1f] %s\n" % (st, en, tx))
            print("%6.1f - %6.1f  %s" % (st, en, tx))
    print("saved", out)
    os.remove(m4s)


if __name__ == "__main__":
    main()

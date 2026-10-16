#!/usr/bin/env python3
"""按 narration.json 逐段生成配音，写出 audio/<段名>.mp3、audio/<段名>.words.json（逐字时间戳）和 audio/durations.json。
转录结果和旁白不一致的地方会打印出来，用来发现 TTS 读错的词。
用法：gen_audio.py [项目目录] [--voice ID] [--emotion 情绪] [--only 段名,段名]
narration.json 的值可以是字符串，也可以是 {"text": 屏幕和对齐用的文本, "tts": 送给 TTS 的读法}。
"""
import argparse, json, math, pathlib, re, subprocess, time
from difflib import SequenceMatcher

p = argparse.ArgumentParser()
p.add_argument("dir", nargs="?", default=".")
p.add_argument("--voice", default="Chinese (Mandarin)_Warm_Girl")
p.add_argument("--emotion", default="happy")
p.add_argument("--only", default="")
a = p.parse_args()
root = pathlib.Path(a.dir)
(root / "audio").mkdir(exist_ok=True)
narr = json.loads((root / "narration.json").read_text())
only = set(filter(None, a.only.split(",")))


def chars(s):
    return "".join(c for c in s if re.match(r"\w", c))


def valid(segs, dur):
    return isinstance(segs, list) and segs and all(
        isinstance(s, dict) and isinstance(s.get("text"), str) and isinstance(s.get("start"), (int, float))
        and math.isfinite(s["start"]) and 0 <= s["start"] <= dur + 0.5 for s in segs)


def duration(mp3):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp3)],
                                capture_output=True, text=True, check=True).stdout)


def transcribe(mp3, out):
    """转录成功且有逐字时间戳时返回听到的文本，否则删掉 out 并返回 None。"""
    for _ in range(3):
        try:
            r = subprocess.run(["mmx", "speech", "transcribe", "--non-interactive", "--quiet", "--file", str(mp3),
                                "--language", "zh", "--response-format", "verbose_json", "--timestamp-level", "word",
                                "--out", str(out)], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=180)
            if r.returncode == 0:
                segs = json.loads(out.read_text()).get("segments")
                if valid(segs, duration(mp3)):
                    return "".join(s["text"] for s in segs)
        except (subprocess.TimeoutExpired, ValueError, AttributeError, OSError):
            pass
        time.sleep(3)
    out.unlink(missing_ok=True)
    return None


for k, v in narr.items():
    if only and k not in only:
        continue
    spoken = v["tts"] if isinstance(v, dict) else v
    mp3, words = root / "audio" / f"{k}.mp3", root / "audio" / f"{k}.words.json"
    subprocess.run(["mmx", "speech", "synthesize", "--non-interactive", "--quiet", "--voice", a.voice,
                    "--language", "Chinese", "--emotion", a.emotion, "--text", spoken, "--out", str(mp3)],
                   check=True, stdin=subprocess.DEVNULL, timeout=180)
    heard = transcribe(mp3, words)
    if heard is None:
        print(f"{k}: 转录失败，这段按字数估算时间")
        continue
    sm = SequenceMatcher(None, chars(spoken), chars(heard), autojunk=False)
    diffs = [f"「{sm.a[i1:i2]}」听成「{sm.b[j1:j2]}」" for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal"]
    if diffs:
        print(f"{k}: 转录和旁白不一致：" + "，".join(diffs))

dur = {k: round(duration(root / "audio" / f"{k}.mp3"), 3) for k in narr}
(root / "audio" / "durations.json").write_text(json.dumps(dur, indent=1))
print(json.dumps(dur, ensure_ascii=False), "total", round(sum(dur.values()), 1))

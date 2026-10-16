#!/usr/bin/env python3
"""按 timeline.json 抽帧拼图：每个 until 短语前后各一帧（前一刻、1 秒后），每段淡出前一帧。
用法：contact_sheet.py <视频> [项目目录]
输出 <项目目录>/contact_sheet_<n>.png，每张最多 12 帧。依赖系统 Python 的 Pillow。
"""
import json, pathlib, subprocess, sys, tempfile
from PIL import Image

video = sys.argv[1]
root = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else ".")
times = []
for sec in json.loads((root / "timeline.json").read_text()):
    points = sec["cues"] + [sec["end"]]
    for i, t in enumerate(sec["cues"]):
        times += [t - 0.05, min(t + 1.0, points[i + 1] - 0.05)]
    times.append(sec["end"] - 0.05)
    subtitles=sec.get("subtitles",[])
    if subtitles:
        longest=max(subtitles,key=lambda c:("\n" in c["text"] or len(c["text"])>24,len(c["text"])))
        times.append((longest["start"]+longest["end"])/2)
times=sorted(set(max(0,t) for t in times))
for old in root.glob("contact_sheet_*.png"):
    old.unlink()
tmp = pathlib.Path(tempfile.mkdtemp())
ims = []
for i, t in enumerate(times):
    f = tmp / f"{i}.png"
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-ss", f"{max(t, 0):.2f}", "-i", video,
                    "-frames:v", "1", "-vf", "scale=640:-1", str(f)], check=True)
    ims.append(Image.open(f))
w, h = ims[0].size
for page in range(0, len(ims), 12):
    chunk = ims[page:page + 12]
    sheet = Image.new("RGB", (w * 3, h * ((len(chunk) + 2) // 3)))
    for i, im in enumerate(chunk):
        sheet.paste(im, ((i % 3) * w, (i // 3) * h))
    out = root / f"contact_sheet_{page // 12 + 1}.png"
    sheet.save(out)
    print(out)

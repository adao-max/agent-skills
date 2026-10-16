#!/usr/bin/env python3
"""核对完整成片的每条字幕与配音时间，失败时返回非零退出码。"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image
from manim import Camera, tempconfig


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video",type=Path)
    parser.add_argument("project",nargs="?",type=Path,default=Path.cwd())
    args=parser.parse_args()
    video=args.video.resolve()
    project=args.project.resolve()
    os.chdir(project)
    import explainer_base as base
    out=project/"qa"
    frames=out/"subtitles"
    frames.mkdir(parents=True,exist_ok=True)
    sections=json.loads(Path("timeline.json").read_text())
    info=json.loads(subprocess.check_output(["ffprobe","-v","error","-show_streams",
        "-show_format","-of","json",str(video)],timeout=30))
    streams=info["streams"]
    if not any(s["codec_type"]=="audio" for s in streams):
        raise ValueError("成片没有音轨")
    v=next(s for s in streams if s["codec_type"]=="video")
    width,height=v["width"],v["height"]
    if len({s["key"] for s in sections})!=len(sections) or {s["key"] for s in sections}!=set(base.N):
        raise ValueError("timeline 的段名必须完整覆盖 narration.json，且不能重复")
    results,issues=[],[]

    def mask(a, threshold=205):
        return np.asarray(a)[int(height*.82):,:,:3].min(axis=2)>threshold
    def expanded(a):
        padded=np.pad(a,1)
        result=a.copy()
        for dy in range(3):
            for dx in range(3):
                result |= padded[dy:dy+a.shape[0],dx:dx+a.shape[1]]
        return result

    for sec in sections:
        key=sec["key"]
        if "subtitles_enabled" not in sec:
            raise ValueError("timeline 缺少字幕记录，请使用共享 ExplainerScene 重新渲染")
        cues=sec["subtitles"]
        if sec["subtitles_enabled"]:
            relative=base.subtitle_cues(key)
            if len(cues)!=len(relative) or any(c["text"]!=r["text"] or c["estimated"]!=r["estimated"] or
                abs(c["start"]-sec["start"]-r["start"])>.05 or
                abs(c["end"]-sec["start"]-r["end"])>.05 for c,r in zip(cues,relative)):
                raise ValueError(f"{key} 的字幕记录与旁白或配音时间不一致")
        elif cues:
            raise ValueError(f"{key} 已禁用字幕却存在字幕记录")
        frame=sec["subtitle_frame"]
        with tempconfig({"frame_width":frame["width"],"frame_height":frame["height"]}):
            camera=Camera(pixel_width=width,pixel_height=height,
                frame_width=frame["width"],frame_height=frame["height"],background_color=base.BG)
            for i,cue in enumerate(cues):
                sample=(cue["start"]+cue["end"])/2
                path=frames/f"{key}-{i:02d}.png"
                subprocess.run(["ffmpeg","-nostdin","-v","error","-y","-ss",f"{sample:.5f}",
                    "-i",str(video),"-frames:v","1",str(path)],check=True,timeout=30)
                card=base.subtitle_card(cue["text"])
                camera.reset()
                camera.capture_mobjects([card])
                expected=mask(camera.pixel_array)
                with Image.open(path) as image:
                    rgb=np.asarray(image.convert("RGB"))
                    actual=mask(rgb)
                    weak=mask(rgb,175)
                if not expected.any():
                    raise ValueError("字幕参考图为空")
                iou=(actual&expected).sum()/max(1,(actual|expected).sum())
                tolerant=expanded(weak)
                recall=(expected&tolerant).sum()/expected.sum()
                columns=np.flatnonzero(expected.any(axis=0))
                groups=np.split(columns,np.flatnonzero(np.diff(columns)>1)+1)
                minimum=min((expected[:,g]&tolerant[:,g]).sum()/expected[:,g].sum() for g in groups)
                passed=bool(iou>.87 and recall>.985 and minimum>.93)
                record={**cue,"key":key,"sample":sample,"frame":str(path),"passed":passed,
                    "iou":float(iou),"glyph_coverage":float(recall),"min_stroke_coverage":float(minimum)}
                results.append(record)
                if not passed:
                    issues.append(f"{key} 第{i+1}条字幕未完整显示或时间错误：{cue['text']}")
                if cue["estimated"]:
                    issues.append(f"{key} 第{i+1}条字幕时间无法可靠定位，请检查对应 words.json：{cue['text']}")
    audio_check=subprocess.run([sys.executable,str(Path(__file__).with_name("check_audio_sync.py")),
        str(video),"--out",str(out/"audio-sync")],capture_output=True,text=True,timeout=300)
    if audio_check.returncode:
        issues.append("音轨时间检查失败："+(audio_check.stdout+audio_check.stderr).strip())
    subprocess.run(["ffmpeg","-nostdin","-v","error","-i",str(video),"-f","null","-"],
        check=True,timeout=180)
    payload={"video":str(video),"passed":not issues,"issues":issues,"subtitles":results,
        "estimated_subtitles":[r for r in results if r["estimated"]]}
    (out/"video-check.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n")
    print(f"成片核验：{'通过' if not issues else '未通过'}。字幕字形：{sum(r['passed'] for r in results)}/{len(results)}；音轨时间："
          +("通过" if audio_check.returncode==0 else "未通过"))
    for issue in issues:
        print(issue)
    return 1 if issues else 0


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (ValueError,KeyError,OSError,subprocess.SubprocessError) as error:
        print(f"成片核验失败：{error}",file=sys.stderr)
        raise SystemExit(2)

"""共享场景基类。项目用符号链接引入，场景代码 `from explainer_base import *`。

每段旁白的写法：
    self.start("s1")          # 播放配音并自动显示同步字幕
    self.until("某个短语")      # 等旁白读到这个短语，再播下一个动画
    self.finish()             # 等配音读完，清理字幕并淡出画面
until 用 audio/<段名>.words.json 里的逐字时间戳定位短语，没有这个文件时按字数估算。
渲染结束时：
- 动画太长、赶不上旁白的，报错并列出。
- 短语没在转录里找到、只能估算的，打印提示。
- 把每段起止、字幕全文与时间、动画短语的实际时间写进 timeline.json，供抽帧与成片核验。
"""
from manim import *
from difflib import SequenceMatcher
import json, math, os, re
import manimpango

_RAW = json.load(open("narration.json"))
N = {k: (v["text"] if isinstance(v, dict) else v) for k, v in _RAW.items()}
SPOKEN = {k: (v["tts"] if isinstance(v, dict) else v) for k, v in _RAW.items()}
D = json.load(open("audio/durations.json"))

_FONTS = set(manimpango.list_fonts())
CN = os.environ.get("EXPLAINER_CN_FONT") or next(
    (font for font in ["PingFang SC", "Noto Sans CJK SC", "Microsoft YaHei"] if font in _FONTS), None)
EN = os.environ.get("EXPLAINER_EN_FONT") or next(
    (font for font in ["Helvetica Neue", "DejaVu Sans", "Noto Sans", CN] if font in _FONTS), None)
if CN not in _FONTS or EN not in _FONTS:
    raise RuntimeError("缺少讲解视频字体。请安装 Noto Sans CJK SC，或用 EXPLAINER_CN_FONT、EXPLAINER_EN_FONT 指定已安装字体。")
BG = "#14171c"
MAIN, HI, OK, BAD = "#58C4DD", "#FFD166", "#83C167", "#FC6255"   # 主体、重点、正确、错误


def _chars(s):
    return "".join(c for c in s if re.match(r"\w", c))


def _index(text, phrase):
    if text.count(phrase) != 1:
        raise ValueError(f"until 的短语「{phrase}」要在本段旁白里出现且只出现一次")
    return len(_chars(text[: text.index(phrase)]))


def _words(key):
    try:
        segs = json.load(open(f"audio/{key}.words.json"))["segments"]
    except (OSError, ValueError, KeyError):
        return None
    heard, times = "", []
    for s in segs:
        ok = isinstance(s, dict) and isinstance(s.get("text"), str) and isinstance(s.get("start"), (int, float))
        if not ok or not math.isfinite(s["start"]) or not 0 <= s["start"] <= D[key] + 0.5:
            return None
        c = _chars(s["text"])
        heard += c
        times += [s["start"]] * len(c)
    return (heard, times) if heard else None


def _time_at(key, idx, span_length=1):
    """按 spoken 的字符位置定位音频，字幕不依赖短句是否重复。"""
    base = _chars(SPOKEN[key])
    w = _words(key)
    if not w:
        return D[key] * idx / max(len(base), 1), True
    heard, times = w
    pairs = [(m.a + i, m.b + i) for m in SequenceMatcher(None, base, heard, autojunk=False).get_matching_blocks()
             for i in range(m.size)]
    exact = dict(pairs)
    span = range(idx, idx + span_length)
    if idx in exact and all(exact.get(i) == exact[idx] + i - idx for i in span):
        return times[exact[idx]], False
    before = [(a, times[b]) for a, b in pairs if a < idx] or [(0, 0.0)]
    after = [(a, times[b]) for a, b in pairs if a > idx] or [(len(base), D[key])]
    (a0, t0), (a1, t1) = before[-1], after[0]
    return t0 + (t1 - t0) * (idx - a0) / max(a1 - a0, 1), True


def cue_time(key, phrase):
    """返回动画短语的音频时间和估算标记。动画短语仍须唯一。"""
    text, spoken = N[key], SPOKEN[key]
    if phrase in spoken:
        return _time_at(key, _index(spoken, phrase), len(_chars(phrase)))
    idx, guessed = _spoken_index(key, _index(text, phrase))
    t, estimated = _time_at(key, idx)
    return t, guessed or estimated


def _spoken_index(key, idx):
    """用相同文字定位读法，长度不同的替换只影响该替换区间。"""
    text, spoken = _chars(N[key]), _chars(SPOKEN[key])
    if text == spoken:
        return idx, False
    matcher = SequenceMatcher(None,text,spoken,autojunk=False)
    for block in matcher.get_matching_blocks():
        if block.a <= idx < block.a+block.size:
            return block.b+idx-block.a, False
    for op,a0,a1,b0,b1 in matcher.get_opcodes():
        if a0 <= idx < a1:
            if op == "replace" and idx == a0 and b1>b0:
                return b0, False
            return round(b0+(idx-a0)/max(a1-a0,1)*(b1-b0)), True
    return len(spoken), True


def cn(s, size=34, color=WHITE, **k):
    return Text(s, font=CN, font_size=size, color=color, **k)


def en(s, size=34, color=WHITE, **k):
    return Text(s, font=EN, font_size=size, color=color, **k)


def fit(m, width):
    """宽度超过 width 时等比缩小。"""
    if m.width > width:
        m.scale_to_fit_width(width)
    return m


def _subtitle_pages(raw):
    spans, offset = [], 0
    for line in raw.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        spans.extend((offset+i, offset+min(i+24,len(content))) for i in range(0,len(content),24))
        offset += len(line)
    return [(raw[spans[i][0]:spans[min(i+1,len(spans)-1)][1]].strip(), spans[i][0])
            for i in range(0,len(spans),2)]


def subtitle_cues(key):
    """生成完整旁白字幕，相对时间按字符位置映射到配音。"""
    text, cues = N[key], []
    for match in re.finditer(r".+?(?:[，。！？：；]|$)", text, re.S):
        for page, offset in _subtitle_pages(match.group()):
            if not _chars(page):
                continue
            idx = len(_chars(text[:match.start()+offset]))
            idx, guessed = _spoken_index(key,idx)
            t, estimated = _time_at(key,idx)
            cues.append({"text":page,"start":t,"estimated":guessed or estimated})
    if _chars("".join(c["text"] for c in cues)) != _chars(text):
        raise ValueError(f"{key} 的字幕未完整覆盖旁白")
    for i,cue in enumerate(cues):
        cue["end"] = cues[i+1]["start"] if i+1<len(cues) else D[key]
        if not 0 <= cue["start"] < cue["end"] <= D[key]+.05:
            raise ValueError(f"{key} 的字幕时间不递增：{cue['text']}")
    if not cues:
        raise ValueError(f"{key} 没有可显示的字幕")
    return cues


def subtitle_card(text):
    lines=[]
    for line in text.splitlines():
        lines.extend(line[i:i+24] for i in range(0,len(line),24))
    if not 1 <= len(lines) <= 2:
        raise ValueError("每条字幕最多两行，请用 subtitle_cues 分页")
    words=cn(lines[0],31) if len(lines)==1 else VGroup(*[cn(line,31) for line in lines]).arrange(DOWN,buff=.14,aligned_edge=LEFT)
    fit(words,config.frame_width-.8)
    if words.height>.92:
        if 31*.92/words.height < 22:
            raise ValueError("字幕字号会小于22，请拆成更短的字幕")
        words.scale_to_fit_height(.92)
    words.move_to([0,-config.frame_height/2+.5+words.height/2,0]).set_z_index(21)
    background=RoundedRectangle(width=config.frame_width-1.1,height=words.height+.22,
        corner_radius=.1,stroke_width=0,fill_color=BG,fill_opacity=.96)
    background.move_to(words).set_z_index(20)
    return VGroup(background,words)


class ExplainerScene(Scene):
    SECTIONS: list = []        # 段名顺序，默认按 narration.json 的顺序
    SUBTITLES = True

    def setup(self):
        if os.path.exists("timeline.json"):
            os.remove("timeline.json")
        self.camera.background_color = BG
        self.late, self.guessed, self.timeline = [], [], []
        self.caption, self.caption_text = None, ""

    def construct(self):
        for k in self.SECTIONS or list(N):
            getattr(self, k)()

    def start(self, key):
        self.key, self.t0 = key, self.renderer.time
        if self.caption is not None:
            raise RuntimeError("开始下一段前必须调用 finish()")
        record={"key":key,"start":self.t0,"cues":[],"subtitles_enabled":self.SUBTITLES,
                "subtitle_frame":{"width":config.frame_width,"height":config.frame_height},"subtitles":[]}
        self.timeline.append(record)
        self.add_sound(f"audio/{key}.mp3")
        if self.SUBTITLES:
            cues=subtitle_cues(key)
            self.guessed.extend(f"{key}字幕「{c['text']}」" for c in cues if c["estimated"])
            record["subtitles"]=[{**c,"start":self.t0+c["start"],"end":self.t0+c["end"]} for c in cues]
            cards=[subtitle_card(c["text"]) for c in cues]
            caption=VGroup(cards[0][0].copy(),VMobject())
            state=[-2]
            def update(m, dt):
                elapsed=self.renderer.time-self.t0
                idx=next((i for i in range(len(cues)-1,-1,-1)
                          if cues[i]["start"]<=elapsed<cues[i]["end"]),-1)
                if idx!=state[0]:
                    if idx>=0:
                        m[0].become(cards[idx][0]).set_z_index(20)
                    m[1].become(cards[idx][1] if idx>=0 else VMobject()).set_z_index(21)
                    m[0].set_opacity(.96 if idx>=0 else 0)
                    self.caption_text=cues[idx]["text"] if idx>=0 else ""
                    state[0]=idx
            caption.add_updater(update)
            self.caption=caption
            self.add(caption)

    def until(self, phrase):
        t, guessed = cue_time(self.key, phrase)
        if guessed:
            self.guessed.append(f"{self.key}「{phrase}」")
        gap = self.t0 + t - self.renderer.time
        if gap > 0.03:
            self.wait(gap)
        elif gap < -0.3:
            self.late.append(f"{self.key}「{phrase}」晚了 {-gap:.1f} 秒")
        self.timeline[-1]["cues"].append(self.renderer.time)

    def finish(self, pad=0.5, fade=0.5):
        rest = self.t0 + D[self.key] + pad - self.renderer.time
        if rest > 0.05:
            self.wait(rest)
        elif rest < -0.3:
            self.late.append(f"{self.key} 的动画比配音长 {-rest:.1f} 秒")
        if self.caption is not None:
            self.caption.clear_updaters()
        self.caption, self.caption_text = None, ""
        self.timeline[-1]["end"] = self.renderer.time
        if self.mobjects:
            self.play(*[FadeOut(m) for m in self.mobjects], run_time=fade)

    def tear_down(self):
        if self.guessed:
            print("这些短语的时间是估算的，预览时重点看：" + "、".join(self.guessed))
        if self.late:
            raise RuntimeError("画面跟不上旁白，缩短这些动画的 run_time 或删减动画：\n" + "\n".join(self.late))
        json.dump(self.timeline, open("timeline.json", "w"), indent=1)

---
name: explainer-video
description: 用 Manim 代码画动画、配中文旁白，做 3Blue1Brown 风格的概念讲解视频（explainer video），1 到 5 分钟，交付 1080p MP4。用户要用视频或动画讲解一个概念、算法、模型结构、论文、规范或机制时使用，例如"做个视频讲讲 X""用动画讲解 X""3b1b 风格讲一下"。
---

# 程序化讲解视频

## 环境

- 安装 Manim：`uv tool install manim`。如果报 pycairo 找不到 pkg-config，先运行 `brew install pkgconf`。
- 配音和转录用 MiniMax 的命令行工具 `mmx`。安装：`npm install -g mmx-cli`，再用 `mmx auth login --api-key <你的 MiniMax API Key>` 登录。如果 `mmx` 报未登录或余额不足，停下来告诉用户。
- `contact_sheet.py` 用系统 Python 的 Pillow，还要用 `ffmpeg` 和 `ffprobe`（`brew install ffmpeg`）。
- macOS 默认用 PingFang SC。Linux 先安装中文字体，例如 Debian/Ubuntu 的 `fonts-noto-cjk`。基类会检查字体是否存在，缺失时停止。自定义字体用 `EXPLAINER_CN_FONT` 和 `EXPLAINER_EN_FONT` 指定，字体必须支持正文中的字符。其他系统用对应包管理器安装 Manim、Pillow 和 FFmpeg。
- 网上的 3Blue1Brown 示例多数是 `manimlib` 写的，API 和 Manim Community 不同，不要直接照抄。
- 本 Skill 的 `scripts/`：
  - `gen_audio.py`：生成配音和逐字时间戳。
  - `explainer_base.py`：场景基类、字幕切分、计时、排版和清理。
  - `contact_sheet.py`：按动画节点及每段最长字幕抽帧拼图，优先检查两行字幕的布局。
  - `verify_video.py`：核对完整成片的字幕字形、配音时间和解码结果。
  - `test_subtitles.py`：用真实 Manim 渲染复现旧故障并验证字幕回归。

## 流程

项目目录放在 `~/video-studio/explainers/<主题>/`。

1. 写提纲。按"提出问题 → 具体例子 → 例子怎么变化 → 一般规则 → 用新例子检验 → 回答开头的问题"的顺序，拆成 5 到 10 段，每段只讲一个点。如果总长超过 3 分钟，先把提纲发给用户确认。
2. 写 `narration.json`。键是段名（`s1`、`s2`……），值是旁白。旁白写成口语，短句，一句只讲一件事。装了 `chinese-writing-style` Skill 时按它写，每段 3 到 6 句。如果 TTS 可能读错某个英文词或缩写，把值写成 `{"text": "屏幕和对齐用的文本", "tts": "送给 TTS 的读法"}`。
3. 运行 `python3 <skill>/scripts/gen_audio.py <项目目录>`。讲解旁白默认音色是 `Chinese (Mandarin)_Warm_Girl`。年份、日期和其他数字在 `tts` 中写成中文读法，`text` 保留屏幕上的阿拉伯数字。只重做某几段时，加 `--only s3,s5`。如果输出"转录和旁白不一致"，判断是不是 TTS 读错了关键词。如果读错了，改那段的 `tts`，用 `--only` 重做。缺少逐字时间戳时先补转录，字幕不能按整段字数比例估时后交付。
4. 用符号链接引入共享 `scripts/explainer_base.py`，再写 `scene.py`。已有项目先移除本地字幕实现及 `start`/`finish` 重写，保留画面逻辑，再备份旧基类、换成链接。项目只编写讲解画面，旁白字幕由基类统一生成。
5. 在项目目录运行 `manim -ql --disable_caching scene.py <类名>`。如果报"画面跟不上旁白"，按报错缩短对应动画的 `run_time` 或删掉动画，再重新渲染。
6. 运行 `python3 <skill>/scripts/contact_sheet.py <预览视频> <项目目录>`，看每张拼图。检查字幕布局、元素重叠和箭头方向。估算时间的动画短语，须对照 `audio/<段名>.words.json` 中前后字的时间确认。
7. 运行 `manim --resolution 1920,1080 --frame_rate 30 --disable_caching scene.py <类名>`。`-qh` 是 60 fps，不要用。用安装 Manim 的 Python 运行 `<skill>/scripts/verify_video.py <成片> <项目目录>`。`uv tool install manim` 对应的解释器是 `$(uv tool dir)/manim/bin/python`。
8. 校验命令必须退出码为 0，且 `qa/video-check.json` 的 `passed` 为 true。字形、音轨时间或字幕定位失败时，查看报告、截图和对应 `words.json`，修复后重新渲染、校验。估算字幕不能仅凭截图放行。
9. 校验通过后复制为 `<主题>-讲解.mp4`，把视频路径告诉用户，当前环境能发文件时直接发给用户。删掉 `media/` 下的低清预览。

## 场景代码

```python
from explainer_base import *

class Topic(ExplainerScene):
    def s1(self):
        self.start("s1")              # 播放配音并自动显示同步字幕
        title = cn("学习率", 60, HI)
        self.play(Write(title))
        self.until("学习率太小")       # 等旁白读到这个短语
        self.play(title.animate.to_edge(UP))
        self.finish()                 # 等配音读完，清理字幕并淡出画面
```

- 每段写一个和段名同名的方法。
- 不要在项目内重写 `start`、`finish` 或字幕 updater。用户明确不要字幕时，设置类属性 `SUBTITLES = False`。
- 段内换画面只淡出或移除自己创建的对象，保留基类字幕。不要对全部 `self.mobjects` 清屏或调用 `self.clear()`。
- `until` 的短语必须原样出现在这段旁白的 `text` 里，并且只出现一次。
- 中文用 `cn()`，英文用 `en()`。字号不小于 22。
- 只用基类的 4 个颜色：`MAIN` 主体，`HI` 重点，`OK` 正确，`BAD` 错误。一个颜色全片只表示一种含义。
- 一屏最多放 3 组元素。新内容进来前，先淡出不再讲的内容。
- 画面底部 20% 留给旁白字幕，图表和说明文字放在这一区域上方。
- 旁白讲到哪个东西，那个东西就出现、变色或移动。

## 常见坑

- 修改共享字幕代码后，用安装 Manim 的 Python 运行 `test_subtitles.py`。它必须通过真实等待、段间切换、两行字幕、重复短句、长句分页和不同读法的对齐检查。只手动修改 `renderer.time` 并调用 updater，无法验证 Manim 的静态等待行为。
- `Text` 不会自动换行，长句用 `\n` 断行。
- 放进外框的文字，用 `fit(文字, 外框宽度 * 0.8)` 限宽。
- 用 `Cross` 划掉选项时，只叉文字，不叉箭头，箭头改成 `BAD` 颜色。
- 给句子里的单词上色，用 `Text(..., t2c={"单词": 颜色})`。

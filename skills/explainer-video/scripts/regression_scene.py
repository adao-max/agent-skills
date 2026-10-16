"""只通过真实渲染时的 update_mobjects 观测，不额外添加 updater。"""
from explainer_base import *
from pathlib import Path


def caption_text(mobject):
    if mobject is None:
        return ''
    return '\n'.join(m.text for m in mobject.get_family() if isinstance(m, Text))


def safe_bounds(mobject):
    if mobject is None:
        return True
    text_objects = [m for m in mobject.get_family() if isinstance(m, Text)]
    return all(m.get_left()[0] >= -config.frame_width / 2 + .10
               and m.get_right()[0] <= config.frame_width / 2 - .10
               and m.get_bottom()[1] >= -config.frame_height / 2 + .10
               and m.get_top()[1] <= config.frame_height / 2 - .10 for m in text_objects)


class SubtitleRegression(ExplainerScene):
    SECTIONS = ['waiting', 'repeated', 'long', 'tts_alias']

    def setup(self):
        super().setup()
        assert isinstance(cn('第一行\n第二行'), Text), 'cn 的公共 Text 类型被改变'
        self.trace = []
        self.cleanup_checks = []
        self.phase = 'setup'
        card = subtitle_card('第一行字幕完整显示\n第二行字幕也完整显示')
        texts = [m for m in card.get_family() if isinstance(m, Text)]
        if len(texts) == 1:
            line_count = len(texts[0].text.splitlines())
        else:
            line_count = len(texts)
        backgrounds = [m for m in card.get_family() if isinstance(m, RoundedRectangle)]
        surrounded = bool(backgrounds) and all(
            m.get_left()[0] >= backgrounds[0].get_left()[0]
            and m.get_right()[0] <= backgrounds[0].get_right()[0]
            and m.get_bottom()[1] >= backgrounds[0].get_bottom()[1]
            and m.get_top()[1] <= backgrounds[0].get_top()[1] for m in texts)
        Path('geometry.json').write_text(json.dumps({'line_count': line_count,
            'safe': safe_bounds(card), 'surrounded': surrounded,
            'bounds': {'bottom': float(card.get_bottom()[1]), 'height': float(card.height)}}))

    def update_mobjects(self, dt):
        super().update_mobjects(dt)
        caption = getattr(self, 'caption', None)
        if getattr(self, 'key', None) is not None:
            text = getattr(self, 'caption_text', caption_text(caption))
            if text and caption is not None:
                words = caption[1]
                safe = (words.get_left()[0] >= -config.frame_width / 2 + .10
                        and words.get_right()[0] <= config.frame_width / 2 - .10
                        and words.get_bottom()[1] >= -config.frame_height / 2 + .10
                        and words.get_top()[1] <= config.frame_height / 2 - .10)
            else:
                safe = True
            self.trace.append({'time': self.renderer.time, 'key': self.key,
                               'phase': self.phase, 'text': text,
                               'safe': bool(safe)})

    def end_segment(self):
        self.phase = 'finish'
        self.finish(pad=.1, fade=.1)
        caption = getattr(self, 'caption', None)
        self.cleanup_checks.append(caption is None or caption not in self.mobjects)

    def waiting(self):
        self.start('waiting')
        self.phase = 'wait'
        self.wait(1.4)
        self.phase = 'until'
        self.until('等待阶段最后一句话')
        self.end_segment()

    def repeated(self):
        self.start('repeated')
        self.phase = 'wait'
        self.wait(1.7)
        self.end_segment()

    def long(self):
        self.start('long')
        self.end_segment()

    def tts_alias(self):
        self.start('tts_alias')
        self.end_segment()

    def tear_down(self):
        super().tear_down()
        Path('caption_trace.json').write_text(json.dumps(self.trace, ensure_ascii=False))
        Path('cleanup.json').write_text(json.dumps(self.cleanup_checks))

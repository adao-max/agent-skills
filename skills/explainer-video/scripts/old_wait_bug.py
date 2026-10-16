"""旧写法的最小失败样本。真实 wait 会冻结没有 dt 的 updater。"""
from manim import *
import json
from pathlib import Path


class OldWaitBug(Scene):
    def construct(self):
        self.changes = []
        label = Text('FIRST', font_size=34)

        def update_caption(m):
            phrase = 'FIRST' if self.renderer.time < 1 else 'SECOND'
            self.changes.append({'time': self.renderer.time, 'text': phrase})
            m.become(Text(phrase, font_size=34))

        label.add_updater(update_caption)
        self.add(label)
        self.wait(2)
        Path('old_wait_trace.json').write_text(json.dumps(self.changes))

"""真实 Manim 回归。测试目录外的文件只读，不调用 TTS 或其他外部服务。"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
DEFAULT_BASE = ROOT / 'explainer_base.py'


def run(args, cwd):
    result = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=180)
    if result.returncode:
        raise RuntimeError(f'命令失败：{args}\n{result.stdout[-18000:]}')
    return result.stdout


def norm(text):
    return ''.join(c for c in text if re.match(r'\w', c))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, default=DEFAULT_BASE)
    parser.add_argument('--work', type=Path)
    options = parser.parse_args()
    work = options.work.resolve() if options.work else Path(tempfile.mkdtemp(prefix='explainer-regressions-'))
    work.mkdir(parents=True, exist_ok=True)
    audio = work / 'audio'
    audio.mkdir(exist_ok=True)
    target = work / 'explainer_base.py'
    if target.exists() or target.is_symlink():
        target.unlink()
    target.symlink_to(options.base.resolve())
    shutil.copy2(ROOT / 'regression_scene.py', work / 'regression_scene.py')
    shutil.copy2(ROOT / 'old_wait_bug.py', work / 'old_wait_bug.py')
    baseline_log = run([sys.executable, '-m', 'manim', '--disable_caching', '--resolution',
                        '854,480', '--frame_rate', '15', 'old_wait_bug.py', 'OldWaitBug'], work)
    (work / 'old_render.log').write_text(baseline_log)
    baseline_trace = json.loads((work / 'old_wait_trace.json').read_text())
    assert 'SECOND' not in {item['text'] for item in baseline_trace}, '旧 bug 没有复现，检查 Manim 环境'
    old_video = work / 'media/videos/old_wait_bug/480p15/OldWaitBug.mp4'
    old_frames = [run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-ss', str(t),
                      '-i', str(old_video), '-frames:v', '1', '-f', 'md5', '-'], work).strip()
                  for t in [.3, 1.5]]
    assert old_frames[0] == old_frames[1], '旧写法视频在等待中切换了字幕，失败样本无效'

    narration = {
        'waiting': '等待阶段第一句话。等待阶段第二句话。等待阶段第三句话。等待阶段最后一句话。',
        'repeated': '继续。继续。继续。',
        'long': '平方表示一个数乘以它自己' * 14 + '这个例子结束了。',
        'tts_alias': {'text':'先讲 API。再讲结果。最后一句。',
                      'tts':'先讲应用程序接口。再讲结果。最后一句。'},
    }
    durations = {'waiting': 4.0, 'repeated': 2.4, 'long': 5.0, 'tts_alias':4.8}
    (work / 'narration.json').write_text(json.dumps(narration, ensure_ascii=False))
    (audio / 'durations.json').write_text(json.dumps(durations))
    for key, duration in durations.items():
        run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
             '-i', f'sine=frequency=440:duration={duration}', '-codec:a', 'libmp3lame',
             '-q:a', '4', str(audio / f'{key}.mp3')], work)
        if key != 'long':
            value=narration[key]
            clean = norm(value['tts'] if isinstance(value,dict) else value)
            step = duration / len(clean)
            segments = [{'text': char, 'start': i * step, 'end': (i + 1) * step}
                        for i, char in enumerate(clean)]
            (audio / f'{key}.words.json').write_text(json.dumps({'segments': segments}, ensure_ascii=False))
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in audio.glob('*.mp3')}
    log = run([sys.executable, '-m', 'manim', '--disable_caching', '--resolution',
               '854,480', '--frame_rate', '15', 'regression_scene.py', 'SubtitleRegression'], work)
    (work / 'render.log').write_text(log)
    assert hashes == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in audio.glob('*.mp3')}, '测试修改了音频原文件'

    timeline = json.loads((work / 'timeline.json').read_text())
    traces = json.loads((work / 'caption_trace.json').read_text())
    geometry = json.loads((work / 'geometry.json').read_text())
    rows = []
    for segment in timeline:
        key = segment['key']
        cues = segment['subtitles']
        assert cues, f'{key} 缺少字幕'
        value=narration[key]
        text=value['text'] if isinstance(value,dict) else value
        assert norm(''.join(cue['text'] for cue in cues)) == norm(text), f'{key} 字幕漏字或重复'
        previous_end = segment['start']
        for cue in cues:
            assert cue['end'] > cue['start'], f'{key} 字幕时间区间为空'
            assert abs(cue['start'] - previous_end) < 0.075, f'{key} 字幕有间隙或重叠'
            previous_end = cue['end']
            midpoint = (cue['start'] + cue['end']) / 2
            nearby = [row for row in traces if row['key'] == key and abs(row['time'] - midpoint) < .13]
            assert nearby, f'{key} 的 {midpoint:.2f}s 没有真实帧更新'
            assert any(norm(row['text']) == norm(cue['text']) for row in nearby), f'{key} 字幕未按时切换：{cue}'
            rows.append({'key': key, 'midpoint': midpoint, 'text': cue['text']})
        assert abs(previous_end - segment['start'] - durations[key]) < .075, f'{key} 末句未覆盖到音频结束'
    assert len(timeline[1]['subtitles']) >= 3, '重复短句没有按位置分开'
    assert len(timeline[2]['subtitles']) >= 4, '长文本没有拆成多页字幕'
    alias=timeline[3]
    alias_words=json.loads((audio/'tts_alias.words.json').read_text())['segments']
    spoken=norm(narration['tts_alias']['tts'])
    for cue in alias['subtitles']:
        if cue['text'] in {'再讲结果。','最后一句。'}:
            expected=alias_words[spoken.index(norm(cue['text']))]['start']
            assert abs(cue['start']-alias['start']-expected)<.001, '英文读法长度变化导致后续字幕错位'
    assert not any(cue['estimated'] for cue in alias['subtitles']), '已可靠定位的不同读法不应整段标成估算'
    for phase in ['wait', 'until', 'finish']:
        values = {norm(row['text']) for row in traces if row['key'] == 'waiting' and row['phase'] == phase and row['text']}
        assert values, f'{phase} 期间字幕没有更新'
        if phase in ['wait', 'until']:
            assert len(values) >= 2, f'{phase} 期间字幕停止切换：{values}'
    assert geometry['line_count'] == 2, f'两行字幕被合并或截断：{geometry}'
    assert geometry['safe'], f'字幕越过屏幕安全边界：{geometry}'
    assert geometry['surrounded'], f'第二行文字越过字幕背景：{geometry}'
    assert all(row['safe'] for row in traces if row['text']), '渲染期间出现越界字幕'
    assert json.loads((work / 'cleanup.json').read_text()) == [True, True, True, True], '上一段字幕未清理'

    video = work / 'media/videos/regression_scene/480p15/SubtitleRegression.mp4'
    assert video.is_file(), f'真实视频不存在：{video}'
    probe = json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(video)], work))
    assert {'audio', 'video'} <= {item['codec_type'] for item in probe['streams']}, '缺少音轨或视频轨'
    frames = work / 'frames'
    frames.mkdir(exist_ok=True)
    for index, row in enumerate(rows):
        run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(row['midpoint']),
             '-i', str(video), '-frames:v', '1', str(frames / f'{index:02d}.png')], work)
    report = {'status': 'PASS', 'subtitle_count': len(rows), 'video': str(video),
              'old_wait_bug': 'REPRODUCED',
              'checks': ['真实 self.wait/updater', 'until 等待', 'finish 等待', '段间清理',
                         '两行安全边界', '重复短句', '长句拆页', '完整文本覆盖', '不同读法的位置对齐', '音频未改动', '实际视频与音轨'],
              'frames': rows}
    (work / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

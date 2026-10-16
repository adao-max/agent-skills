#!/usr/bin/env python3
"""核对成片配音与 timeline 的实际起点及中段偏移。"""
from pathlib import Path
import argparse
import json
import subprocess
import sys

import numpy as np
from scipy.signal import correlate

RATE = 16000
LIMIT_MS = 80.0
MIN_CORRELATION = .65
SEARCH_SECONDS = .4
WINDOW_SECONDS = 1.5


def decode(path):
    result = subprocess.run([
        'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
        '-i', str(path), '-vn', '-ac', '1', '-ar', str(RATE),
        '-f', 'f32le', 'pipe:1',
    ], capture_output=True, timeout=120, check=True)
    return np.frombuffer(result.stdout, dtype='<f4').astype(np.float64)


def compare(output, source, timeline_start, source_start):
    begin = round(source_start * RATE)
    template = source[begin:begin + round(WINDOW_SECONDS * RATE)]
    if len(template) < RATE // 2:
        raise ValueError('源音频不足以截取比较窗口')
    template = template - template.mean()
    power = np.dot(template, template)
    if power < 1e-8:
        raise ValueError('比较窗口没有可辨识的音频')
    expected = timeline_start + begin / RATE
    search_begin = max(0, round((expected - SEARCH_SECONDS) * RATE))
    search_end = min(len(output), round((expected + SEARCH_SECONDS) * RATE) + len(template))
    region = output[search_begin:search_end]
    if len(region) < len(template):
        raise ValueError('成片音轨不足以截取比较窗口')
    numerator = correlate(region, template, mode='valid', method='fft')
    running_sum = np.concatenate(([0.], np.cumsum(region)))
    running_sq = np.concatenate(([0.], np.cumsum(region * region)))
    width = len(template)
    sums = running_sum[width:] - running_sum[:-width]
    squares = running_sq[width:] - running_sq[:-width]
    energies = np.maximum(squares - sums * sums / width, 1e-20)
    normalized = numerator / np.sqrt(energies * power)
    index = int(np.argmax(normalized))
    observed = (search_begin + index) / RATE
    offset_ms = (observed - expected) * 1000
    score = float(normalized[index])
    return {
        'source_window_start': round(begin / RATE, 6),
        'timeline_window_start': round(expected, 6),
        'observed_window_start': round(observed, 6),
        'inferred_section_start': round(observed - begin / RATE, 6),
        'offset_ms': round(offset_ms, 3),
        'correlation': round(score, 6),
        'passed': abs(offset_ms) <= LIMIT_MS and score >= MIN_CORRELATION,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path)
    parser.add_argument('--timeline', type=Path, default=Path('timeline.json'))
    parser.add_argument('--audio-dir', type=Path, default=Path('audio'))
    parser.add_argument('--out', type=Path, default=Path('qa/audio-sync'))
    args = parser.parse_args()
    sections = json.loads(args.timeline.read_text())
    output = decode(args.video)
    results = []
    for section in sections:
        key = section['key']
        source = decode(args.audio_dir / f'{key}.mp3')
        duration = len(source) / RATE
        positions = {'开头': min(.2, max(0., duration - WINDOW_SECONDS)),
                     '中段': max(0., duration / 2 - WINDOW_SECONDS / 2)}
        item = {'key': key, 'timeline_start': section['start'], 'source_duration': duration,
                'checks': {name: compare(output, source, section['start'], start)
                           for name, start in positions.items()}}
        item['passed'] = all(check['passed'] for check in item['checks'].values())
        results.append(item)
        print(key, 'PASS' if item['passed'] else 'FAIL',
              ', '.join(f"{name} {check['offset_ms']:+.3f}ms r={check['correlation']:.4f}"
                        for name, check in item['checks'].items()))
    passed = all(item['passed'] for item in results)
    payload = {'video': str(args.video), 'timeline': str(args.timeline),
               'sample_rate': RATE, 'limit_ms': LIMIT_MS,
               'minimum_correlation': MIN_CORRELATION, 'passed': passed, 'sections': results}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.with_suffix('.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    return 0 if passed else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as error:
        print(f'音轨核验失败：{error}', file=sys.stderr)
        sys.exit(2)

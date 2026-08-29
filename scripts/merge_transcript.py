"""Слияние распознанных таймингов с точным текстом сценария.

Whisper ошибается на слух, но точный текст обычно уже есть — тогда берём
у распознавания только тайминги, а слова подставляем из сценария.

Ключевое: в результат обязаны попасть ВСЕ слова сценария. Наивная версия
отбрасывала непарные, и из субтитров пропадали куски ("бинарность м/ж" ->
"бинарность"), после чего текст расходился с речью.

    python merge_transcript.py words.json script.txt out.json
"""
import difflib
import json
import re
import sys


def norm(s):
    return re.sub(r'[^\w]', '', s.lower(), flags=re.UNICODE)


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    words_path, script_path, out_path = sys.argv[1:4]

    words = json.load(open(words_path, encoding='utf-8'))
    script = re.sub(r'\s+', ' ', open(script_path, encoding='utf-8').read().strip()).split(' ')

    a = [norm(x['w']) for x in words]
    b = [norm(x) for x in script]

    merged = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        src, dst = words[i1:i2], script[j1:j2]
        if not dst:
            continue                       # распознано лишнее — выбрасываем
        if src:
            start, end = src[0]['s'], src[-1]['e']
        else:                              # слово сценария, которого нет в распознанном
            start = end = merged[-1]['e'] if merged else 0.0
        span = max(end - start, 0.04 * len(dst))
        step = span / len(dst)
        for k, w in enumerate(dst):
            merged.append({'w': w,
                           's': round(start + k * step, 3),
                           'e': round(start + (k + 1) * step, 3)})

    merged = [x for x in merged if x['w']]

    # Формат openai-whisper: сегмент на предложение. Его ждут сторонние
    # инструменты субтитров, поэтому отдаём именно так.
    segments, cur = [], []
    for x in merged:
        cur.append({'start': x['s'], 'end': x['e'], 'word': ' ' + x['w']})
        if re.search(r'[.!?]$', x['w']) and len(cur) >= 3:
            segments.append({'start': cur[0]['start'], 'end': cur[-1]['end'],
                             'text': ' '.join(w['word'].strip() for w in cur),
                             'words': cur})
            cur = []
    if cur:
        segments.append({'start': cur[0]['start'], 'end': cur[-1]['end'],
                         'text': ' '.join(w['word'].strip() for w in cur), 'words': cur})

    json.dump({'text': ' '.join(x['w'] for x in merged), 'segments': segments},
              open(out_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'{out_path}: {len(segments)} сегментов, {len(merged)} слов')


if __name__ == '__main__':
    main()

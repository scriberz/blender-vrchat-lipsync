"""Сборка рилса: PNG-секвенция аватара + фон + хук + субтитры -> 1080x1920.

Аватар рендерится с прозрачным фоном, поэтому кладётся слоем на подложку.
Субтитры намеренно спокойные, в нижней трети: крупное караоке дерётся с лицом
за внимание и убивает смысл липсинка. Хук — одна фраза на первые секунды.

  python compose_reel.py <frames_dir> <words.json> <wav> <out.mp4> [fps] [sec] ["хук"]
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# ffmpeg берём из PATH; переопределяется переменными FFMPEG / FFPROBE
FF = Path(os.environ.get('FFMPEG') or shutil.which('ffmpeg') or 'ffmpeg')
FONTS = Path(os.environ.get('FONTS_DIR', ROOT / 'fonts'))

frames = Path(sys.argv[1])
words_json = Path(sys.argv[2])
wav = Path(sys.argv[3])
out = Path(sys.argv[4])
FPS = int(sys.argv[5]) if len(sys.argv) > 5 else 24
SEC = float(sys.argv[6]) if len(sys.argv) > 6 else 14.0
HOOK = sys.argv[7] if len(sys.argv) > 7 else ''

# Хук отключён: пока он висел, субтитры молчали, и произнесённые в это время
# слова просто пропадали — текст переставал соответствовать речи.
HOOK_UNTIL = 0.0

# Размер берём из самих кадров аватара: любое несовпадение даёт видимую
# границу PNG поверх подложки — ту самую "рамку".
FP = Path(os.environ.get('FFPROBE') or shutil.which('ffprobe') or 'ffprobe')
first = sorted(frames.glob('f_*.png'))[0]
probe = subprocess.run([str(FP), '-v', 'error', '-select_streams', 'v:0',
                        '-show_entries', 'stream=width,height', '-of', 'csv=p=0:s=x',
                        str(first)], capture_output=True, text=True).stdout.strip()
W, H = (int(v) for v in probe.split('x'))
print(f'кадр аватара: {W}x{H}')

words = json.load(open(words_json, encoding='utf-8'))
if isinstance(words, dict):
    words = [w for s in words['segments'] for w in s['words']]
words = [{'t': (w.get('word') or w.get('w')).strip(),
          's': float(w.get('start', w.get('s'))),
          'e': float(w.get('end', w.get('e')))} for w in words]
words = [w for w in words if w['s'] < SEC]


def ts(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f'{h}:{m:02d}:{s:05.2f}'


def esc(s):
    return s.replace('{', '(').replace('}', ')').replace('\\', '/')


# В Russo One нет длинного тире и типографских кавычек: libass подставляет на них
# запасной шрифт, и строка выглядит набранной другой гарнитурой.
TYPO = {'—': '-', '–': '-', '«': '"', '»': '"', '“': '"', '”': '"', '„': '"',
        '’': "'", '‘': "'", '…': '...'}


def norm(s):
    for a, b in TYPO.items():
        s = s.replace(a, b)
    return s


# ── ASS: субтитры внизу + хук ───────────────────────────────────────────────
ass = f'''[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: SUB,Russo One,56,&H00FFFFFF,&H000000FF,&H00000000,&HA0000000,0,0,0,0,100,100,0,0,3,20,0,2,90,90,70,204

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''

if HOOK:
    text = esc(norm(HOOK)).upper().replace('|', r'\N')
    ass += (f'Dialogue: 1,{ts(0)},{ts(HOOK_UNTIL)},SUB,,0,0,0,,'
            f'{{\\an2\\pos({W // 2},{int(H * 0.90)})\\fad(200,260)}}{text}\n')

# Субтитры набираются по длине строки, а не по числу слов: при разном
# количестве строк нижний край стоит, а верхний прыгает — текст "скачет".
MAX_CHARS = 20            # 20 заглавных Russo One при кегле 56 влезают в 900 px
SUB_Y = int(H * 0.90)     # фиксированная точка, блок всегда растёт от неё вверх

# Короткие служебные слова не должны оставаться в конце строки —
# "ПРОСТО ОДНА ИЗ" читается как обрыв. Переносим их к следующей строке.
HANGING = {'и', 'а', 'но', 'в', 'во', 'на', 'с', 'со', 'к', 'ко', 'из', 'от', 'до',
           'по', 'за', 'у', 'о', 'об', 'для', 'что', 'это', 'как', 'же', 'не', 'ни'}

chunks, cur = [], []
for w in [w for w in words if w['e'] > HOOK_UNTIL]:
    probe = ' '.join(x['t'] for x in cur + [w])
    if cur and len(probe) > MAX_CHARS:
        tail = []
        while len(cur) > 1 and cur[-1]['t'].strip('.,!?:;—-').lower() in HANGING:
            tail.insert(0, cur.pop())
        chunks.append(cur)
        cur = tail + [w]
    else:
        cur.append(w)
    # конец предложения — закрываем строку, не тащим фразу через точку
    if cur and re.search(r'[.!?]$', cur[-1]['t']):
        chunks.append(cur)
        cur = []
if cur:
    chunks.append(cur)

for idx, chunk in enumerate(chunks):
    start = max(chunk[0]['s'], HOOK_UNTIL)
    nxt = chunks[idx + 1][0]['s'] if idx + 1 < len(chunks) else None
    end = chunk[-1]['e'] + 0.12
    if nxt is not None:
        end = min(end, nxt)        # встык: иначе соседние строки накладываются
    if end <= start:
        continue
    # капс, как в хуке: один шрифт в двух регистрах читается как два разных
    line = esc(norm(' '.join(x['t'] for x in chunk))).upper()
    ass += (f'Dialogue: 0,{ts(start)},{ts(end)},SUB,,0,0,0,,'
            f'{{\\an2\\pos({W // 2},{SUB_Y})\\fad(120,120)}}{line}\n')

# Файл кладём рядом с выходом и передаём фильтру ОТНОСИТЕЛЬНЫМ путём:
# двоеточие диска в filter_complex ломает парсер, а обратный слэш он съедает.
work = out.resolve().parent
work.mkdir(parents=True, exist_ok=True)
ass_path = work / (out.stem + '.ass')
ass_path.write_text(ass, encoding='utf-8')
ass_rel = ass_path.name
fonts_rel = Path(os.path.relpath(FONTS, work)).as_posix() if FONTS.exists() else '.'

# gradients — источник, а не фильтр: он объявляется отдельной цепочкой,
# иначе граф схлопывается в сплошную заливку и кадр уходит пустым.
graph = (
    f'gradients=s={W}x{H}:c0=0x1a1426:c1=0x080711:r={FPS}:d={SEC}:speed=0.008[bg];'
    # аватар уже отрендерен в полный кадр рилса — кладём один в один, без масштаба
    f'[0:v]format=rgba[av];'
    f'[bg][av]overlay=0:0:format=auto[withav];'
    f'[withav]ass={ass_rel}:fontsdir={fonts_rel},format=yuv420p[v]'
)

cmd = [str(FF), '-y', '-hide_banner', '-loglevel', 'error',
       '-framerate', str(FPS), '-start_number', '1', '-i', str(frames / 'f_%04d.png'),
       '-i', str(wav),
       '-filter_complex', graph,
       '-map', '[v]', '-map', '1:a',
       '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
       '-c:a', 'aac', '-b:a', '160k', '-t', str(SEC),
       '-movflags', '+faststart', str(out)]

r = subprocess.run(cmd, cwd=str(work), capture_output=True, text=True)
print('exit:', r.returncode)
if r.returncode:
    print(r.stderr[-900:])
else:
    print(f'{out} — {out.stat().st_size / 1024 / 1024:.1f} MB')





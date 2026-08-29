"""Word-level тайминги речи через faster-whisper.

    python align_words.py voice.wav words.json

Язык — переменная LANG_CODE (по умолчанию ru). Модель — WHISPER_MODEL
(по умолчанию small). На слабых картах float16 недоступен, тогда идёт CPU int8.
"""
import sys, json, os

WAV = sys.argv[1] if len(sys.argv) > 1 else 'voice.wav'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'words.json'
if os.path.dirname(OUT):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)

from faster_whisper import WhisperModel

try:
    model = WhisperModel(os.environ.get('WHISPER_MODEL', 'small'), device='cuda', compute_type='float16')
    dev = 'cuda'
except Exception as e:
    print('cuda fail:', e)
    model = WhisperModel(os.environ.get('WHISPER_MODEL', 'small'), device='cpu', compute_type='int8')
    dev = 'cpu'

segs, info = model.transcribe(WAV, language=os.environ.get('LANG_CODE', 'ru'), word_timestamps=True, vad_filter=False)
words = []
for s in segs:
    for w in s.words:
        words.append({'w': w.word.strip(), 's': round(w.start, 3), 'e': round(w.end, 3)})

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(words, f, ensure_ascii=False, indent=1)
print(f'{dev} | words={len(words)} | dur={words[-1]["e"] if words else 0}')
print(' '.join(x['w'] for x in words[:20]))



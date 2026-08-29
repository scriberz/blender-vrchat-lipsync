"""Распаковка .unitypackage в human-readable дерево.

Формат: tar.gz, внутри по папке на ассет — файлы `asset` (само содержимое),
`asset.meta` (guid) и `pathname` (исходный путь в проекте Unity). Восстанавливаем
оригинальные имена, иначе Blender не находит текстуры при импорте FBX.

  python rig/unpack_unitypackage.py <pkg.unitypackage> <out_dir>
"""
import sys, tarfile, shutil
from pathlib import Path

pkg = Path(sys.argv[1])
out = Path(sys.argv[2])
tmp = out / '_raw'
if out.exists():
    shutil.rmtree(out)
tmp.mkdir(parents=True)

with tarfile.open(pkg, 'r:gz') as tf:
    tf.extractall(tmp)

count = 0
for d in tmp.iterdir():
    if not d.is_dir():
        continue
    pn, asset = d / 'pathname', d / 'asset'
    if not (pn.exists() and asset.exists()):
        continue
    rel = pn.read_text(encoding='utf-8', errors='ignore').strip().splitlines()[0].strip()
    dst = out / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(asset, dst)
    size = dst.stat().st_size
    print(f'{size/1024:8.0f} KB  {rel}')
    count += 1

shutil.rmtree(tmp, ignore_errors=True)
print(f'\n{count} файлов -> {out}')

"""Длина анимации и кости в FBX-клипе.

  blender -b --python rig/list_anims.py -- <fbx>
"""
import sys
import bpy

path = sys.argv[sys.argv.index('--') + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
try:
    bpy.ops.import_scene.fbx(filepath=path)
except Exception as exc:                      # битые/несовместимые клипы
    print(f'CLIP fail: {exc}')
    sys.exit(0)


def curves_of(action):
    out = []
    if hasattr(action, 'fcurves'):
        out += list(action.fcurves)
    for layer in getattr(action, 'layers', []):
        for strip in layer.strips:
            for cb in getattr(strip, 'channelbags', []):
                out += list(cb.fcurves)
    return out


arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
bones = len(arms[0].data.bones) if arms else 0
prefix = 'mixamo' if arms and any(b.name.startswith('mixamorig') for b in arms[0].data.bones) else 'other'

for a in bpy.data.actions:
    cs = curves_of(a)
    rng = a.frame_range
    print(f'CLIP name={a.name} frames={rng[0]:.0f}-{rng[1]:.0f} '
          f'len={rng[1] - rng[0]:.0f} curves={len(cs)} bones={bones} rig={prefix}')
if not bpy.data.actions:
    print(f'CLIP none bones={bones} rig={prefix}')

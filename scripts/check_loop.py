"""Проверка, что CYCLES реально зацикливает клип: поза на кадре k и k+len должна совпасть.

  blender -b --python rig/check_loop.py -- <idle.fbx>
"""
import sys
import bpy

path = sys.argv[sys.argv.index('--') + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=path)

arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
act = arm.animation_data.action

curves = []
if hasattr(act, 'fcurves'):
    curves += list(act.fcurves)
for layer in getattr(act, 'layers', []):
    for strip in layer.strips:
        for cb in getattr(strip, 'channelbags', []):
            curves += list(cb.fcurves)
for fcu in curves:
    if not fcu.modifiers:
        fcu.modifiers.new('CYCLES')

length = int(act.frame_range[1] - act.frame_range[0])
print(f'curves={len(curves)} length={length}')

bone = arm.pose.bones.get('mixamorig:Head') or arm.pose.bones[0]


def sample(frame):
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()
    return bone.matrix.to_euler()


for k in (5, 40, 90):
    a, b = sample(k), sample(k + length)
    delta = max(abs(a[i] - b[i]) for i in range(3))
    verdict = 'LOOP OK' if delta < 1e-4 else 'NOT LOOPING'
    print(f'frame {k} vs {k + length}: delta={delta:.6f} -> {verdict}')

# насколько жёсткий стык: конец против начала
a, b = sample(1), sample(length)
print(f'seam 1 vs {length}: delta={max(abs(a[i] - b[i]) for i in range(3)):.4f} '
      f'(чем меньше, тем незаметнее склейка)')

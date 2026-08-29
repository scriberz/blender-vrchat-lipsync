"""Полный список костей арматуры.

  blender -b --python rig/dump_bones.py -- <fbx>
"""
import sys
import bpy

path = sys.argv[sys.argv.index('--') + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=path)

for arm in [o for o in bpy.data.objects if o.type == 'ARMATURE']:
    print(f'\n=====ARM {arm.name} ({len(arm.data.bones)})=====')
    for b in arm.data.bones:
        parent = b.parent.name if b.parent else '-'
        print(f'BONE {b.name} <- {parent}')
print('=====END=====')

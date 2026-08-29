"""Что внутри FBX: меши, шейпкеи (визимы), материалы, текстуры, кости.

Запуск:
  blender -b --python rig/inspect_visemes.py -- <path.fbx>
"""
import sys
import bpy

path = sys.argv[sys.argv.index('--') + 1]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=path)

print('\n=====SCAN=====')
for ob in bpy.data.objects:
    if ob.type != 'MESH':
        continue
    sk = ob.data.shape_keys
    keys = list(sk.key_blocks.keys()) if sk else []
    print(f'MESH {ob.name}: verts={len(ob.data.vertices)} shapekeys={len(keys)}')
    visemes = [k for k in keys if 'vrc' in k.lower() or 'viseme' in k.lower()]
    if visemes:
        print('  VISEMES: ' + ', '.join(visemes))
    elif keys:
        print('  KEYS: ' + ', '.join(keys[:25]))
    for slot in ob.material_slots:
        m = slot.material
        if not m:
            continue
        imgs = []
        if m.use_nodes:
            imgs = [n.image.name for n in m.node_tree.nodes
                    if n.type == 'TEX_IMAGE' and n.image]
        print(f'  MAT {m.name}: textures={imgs or "НЕТ"}')

arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
for a in arms:
    print(f'ARMATURE {a.name}: bones={len(a.data.bones)}')
    head = [b.name for b in a.data.bones if 'head' in b.name.lower()]
    print(f'  head bones: {head[:5]}')
print('=====END=====')

"""Превью головы модели: EEVEE, трёхточечный свет, текстуры, камера по кости Head.

Чинит две беды прошлого рига: WORKBENCH без освещения и камеру мимо модели.
Текстуры ищутся рядом с FBX (Unity кладёт их в соседние Textures/Mat папки),
камера ставится по мировой позиции кости Head, а не по угаданным координатам.

  blender -b --python rig/head_preview.py -- <fbx> <out.png> [body|head]
"""
import sys
from pathlib import Path

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index('--') + 1:]
fbx = Path(args[0]).resolve()
out = Path(args[1]).resolve()
shot = args[2] if len(args) > 2 else 'head'

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(fbx))

# ---- текстуры: Unity их не прописывает в FBX, ищем по имени рядом ----
# Ищем строго внутри дерева модели: выше начинаются чужие папки проекта,
# откуда Blender утащит текстуру от другого персонажа.
root = fbx.parent
for _ in range(3):
    if root.parent.name.lower() in ('assets', 'unpacked', 'models') or root.parent == root:
        break
    root = root.parent
tex_files = [p for p in root.rglob('*')
             if p.suffix.lower() in ('.png', '.jpg', '.jpeg') and p.stat().st_size > 4096]
tex_files = sorted(set(tex_files), key=lambda p: -p.stat().st_size)
print('TEXROOT', root, '->', len(tex_files), 'textures')

def pick_texture(mat_name):
    """Текстура по совпадению имени, иначе самая большая (обычно основной атлас)."""
    key = mat_name.lower().split('.')[0]
    for p in tex_files:
        if key and key in p.stem.lower():
            return p
    return tex_files[0] if tex_files else None

for mat in bpy.data.materials:
    if not mat.use_nodes:
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if not bsdf:
        continue
    has_tex = any(n.type == 'TEX_IMAGE' and n.image for n in nt.nodes)
    if has_tex:
        continue
    path = pick_texture(mat.name)
    if not path:
        continue
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(str(path.resolve()))
    tex.interpolation = 'Closest'
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    if 'Alpha' in bsdf.inputs:
        nt.links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])
    mat.blend_method = 'BLEND' if 'hair' in mat.name.lower() else 'OPAQUE'
    bsdf.inputs['Roughness'].default_value = 0.62
    if 'Specular IOR Level' in bsdf.inputs:
        bsdf.inputs['Specular IOR Level'].default_value = 0.25

scene = bpy.context.scene
engines = scene.render.bl_rna.properties['engine'].enum_items.keys()
scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engines else 'BLENDER_EEVEE'
scene.render.resolution_x = 1080
scene.render.resolution_y = 1080 if shot == 'head' else 1920
scene.render.film_transparent = True
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.view_settings.view_transform = 'Standard'

# ---- камера по кости Head, а не по магическим числам ----
arm = next((o for o in bpy.data.objects if o.type == 'ARMATURE'), None)
meshes = [o for o in bpy.data.objects if o.type == 'MESH']

head_bone = None
if arm:
    for name in ('Head', 'head', 'Bip01_Head', 'J_Bip_C_Head'):
        if name in arm.data.bones:
            head_bone = arm.data.bones[name]
            break

if head_bone and shot == 'head':
    target = arm.matrix_world @ head_bone.head_local
    span = (head_bone.tail_local - head_bone.head_local).length
    ortho = max(0.35, span * 3.4)
    target = target + Vector((0, 0, span * 0.55))
else:
    lo = Vector((1e9, 1e9, 1e9)); hi = Vector((-1e9, -1e9, -1e9))
    for m in meshes:
        for corner in m.bound_box:
            w = m.matrix_world @ Vector(corner)
            lo = Vector((min(lo[i], w[i]) for i in range(3)))
            hi = Vector((max(hi[i], w[i]) for i in range(3)))
    target = (lo + hi) / 2
    ortho = max((hi - lo).x, (hi - lo).z) * 1.15

cam_data = bpy.data.cameras.new('Cam')
cam_data.type = 'ORTHO'
cam_data.ortho_scale = ortho
cam = bpy.data.objects.new('Cam', cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
# FBX из Unity приходит Y-forward: лицо смотрит в -Y, камера встаёт спереди
cam.location = target + Vector((0, -ortho * 2.2, 0))
cam.rotation_euler = (1.5708, 0, 0)

# ---- трёхточечный свет ----
def add_light(name, kind, energy, loc, size=2.0):
    d = bpy.data.lights.new(name, kind)
    d.energy = energy
    if kind == 'AREA':
        d.size = size
    o = bpy.data.objects.new(name, d)
    scene.collection.objects.link(o)
    o.location = target + Vector(loc)
    direction = (target - o.location).normalized()
    o.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    return o

s = ortho
add_light('Key', 'AREA', 260 * s * s, (-s * 1.6, -s * 2.0, s * 1.4), size=s * 2)
add_light('Fill', 'AREA', 90 * s * s, (s * 2.0, -s * 1.6, 0), size=s * 2.4)
add_light('Rim', 'AREA', 200 * s * s, (s * 0.6, s * 2.2, s * 1.2), size=s * 1.6)

world = bpy.data.worlds.new('W')
scene.world = world
world.use_nodes = True
world.node_tree.nodes['Background'].inputs[0].default_value = (0.05, 0.05, 0.07, 1)
world.node_tree.nodes['Background'].inputs[1].default_value = 0.35

out.parent.mkdir(parents=True, exist_ok=True)
scene.render.filepath = str(out)
bpy.ops.render.render(write_still=True)
print('SAVED', out)

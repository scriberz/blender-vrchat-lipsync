"""Рендер говорящего аватара: липсинк по визимам vrc.v_*, жесты, моргание.

Отдаёт PNG-секвенцию с прозрачным фоном — фон и субтитры накладывает
compose_reel.py.

    blender -b --python render_avatar.py -- \\
        <avatar.fbx> <words.json> <out_dir> [fps] [max_sec] [anims] [shot]

  anims  — FBX-клипы Mixamo через ';'. Задают позу и жесты, чередуются
           каждые 9 секунд в случайном порядке с плавным переходом.
           Без них персонаж остаётся в T-позе с разведёнными вручную руками.
  shot   — head (по умолчанию) | waist | body | reel
  fps    — по умолчанию 24; max_sec = 0 означает всю длину озвучки

Размер кадра — переменные окружения AVATAR_W / AVATAR_H (по умолчанию 720x900).
"""
import json
import math
import os
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index('--') + 1:]
FBX = Path(args[0]).resolve()
WORDS = Path(args[1]).resolve()
OUT = Path(args[2]).resolve()
FPS = int(args[3]) if len(args) > 3 else 24
MAX_SEC = float(args[4]) if len(args) > 4 else 0.0
# Несколько клипов через ';' — чередуются по SWITCH_SEC, чтобы жестикуляция
# не повторялась на всю длину ролика.
IDLES = [Path(p).resolve() for p in args[5].split(';') if p] if len(args) > 5 and args[5] else []
IDLE = IDLES[0] if IDLES else None
SWITCH_SEC = 9.0
SHOT = args[6] if len(args) > 6 else 'head'   # head | body — body показывает позу целиком

# Mixamo -> кости VRChat-аватара.
# Только корпус и голова: у рук roll костей в двух ригах разный, и копирование
# локальных вращений задирает их над головой. В портретном кадре живость даёт
# именно корпус, а руки ставятся фиксированной A-позой ниже.
RETARGET = {
    'mixamorig:Hips': 'Hips',
    'mixamorig:Spine': 'Spine',
    'mixamorig:Spine1': 'Chest',
    'mixamorig:Neck': 'Neck',
    'mixamorig:Head': 'Head',
    'mixamorig:LeftShoulder': 'Left shoulder',
    'mixamorig:LeftArm': 'Left arm',
    'mixamorig:LeftForeArm': 'Left elbow',
    'mixamorig:RightShoulder': 'Right shoulder',
    'mixamorig:RightArm': 'Right arm',
    'mixamorig:RightForeArm': 'Right elbow',
}

# ── русские буквы → визимы VRChat ───────────────────────────────────────────
VIS = {
    'а': 'aa', 'я': 'aa',
    'о': 'oh', 'ё': 'oh',
    'у': 'ou', 'ю': 'ou',
    'э': 'e', 'е': 'e',
    'и': 'ih', 'ы': 'ih', 'й': 'ih',
    'п': 'pp', 'б': 'pp', 'м': 'pp',
    'ф': 'ff', 'в': 'ff',
    'с': 'ss', 'з': 'ss', 'ц': 'ss',
    'ш': 'ch', 'ж': 'ch', 'щ': 'ch', 'ч': 'ch',
    'т': 'dd', 'д': 'dd',
    'н': 'nn', 'л': 'nn',
    'к': 'kk', 'г': 'kk', 'х': 'kk',
    'р': 'rr',
}
VOWELS = set('аяоёуюэеиы')

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(FBX))

scene = bpy.context.scene
engines = scene.render.bl_rna.properties['engine'].enum_items.keys()
scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engines else 'BLENDER_EEVEE'
# 720x900 вместо 1080x1350: пикселей вдвое меньше, а на телефоне разница
# не видна — модель плоско зашейдена, без отражений и мелких деталей.
# Итоговый ролик апскейлится до 1080 при сборке.
scene.render.resolution_x = int(os.environ.get('AVATAR_W', 720))
scene.render.resolution_y = int(os.environ.get('AVATAR_H', 900))
scene.render.film_transparent = True
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.view_settings.view_transform = 'Standard'
scene.render.fps = FPS

# Персонаж на плоском фоне — трассировать нечего, поэтому режем всё тяжёлое.
# Без этого кадр считается ~2.6 с, что на 292 ролика неподъёмно.
ee = getattr(scene, 'eevee', None)
if ee:
    for attr, value in (('taa_render_samples', 16), ('use_gtao', False),
                        ('use_bloom', False), ('use_ssr', False),
                        ('use_motion_blur', False), ('use_raytracing', False),
                        ('use_shadows', True), ('shadow_ray_count', 1),
                        ('shadow_step_count', 2)):
        if hasattr(ee, attr):
            setattr(ee, attr, value)

# ── текстуры (Unity не прописывает их в FBX) ────────────────────────────────
root = FBX.parent
for _ in range(3):
    if root.parent.name.lower() in ('assets', 'unpacked', 'models') or root.parent == root:
        break
    root = root.parent
tex_files = sorted({p for p in root.rglob('*')
                    if p.suffix.lower() in ('.png', '.jpg', '.jpeg') and p.stat().st_size > 4096},
                   key=lambda p: -p.stat().st_size)


def pick_texture(name):
    key = name.lower().split('.')[0]
    for p in tex_files:
        if key and key in p.stem.lower():
            return p
    return tex_files[0] if tex_files else None


for mat in bpy.data.materials:
    if not mat.use_nodes:
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if not bsdf or any(n.type == 'TEX_IMAGE' and n.image for n in nt.nodes):
        continue
    path = pick_texture(mat.name)
    if not path:
        continue
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(str(path))
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    if 'Alpha' in bsdf.inputs:
        nt.links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])
        mat.blend_method = 'HASHED'
    bsdf.inputs['Roughness'].default_value = 0.6
    if 'Specular IOR Level' in bsdf.inputs:
        bsdf.inputs['Specular IOR Level'].default_value = 0.25

arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')

# ── тайминги слов ───────────────────────────────────────────────────────────
words = json.load(open(WORDS, encoding='utf-8'))
if isinstance(words, dict):
    words = [w for s in words['segments'] for w in s['words']]
words = [{'t': (w.get('word') or w.get('w')).strip().lower(),
          's': float(w.get('start', w.get('s'))),
          'e': float(w.get('end', w.get('e')))} for w in words]
if MAX_SEC:
    words = [w for w in words if w['s'] < MAX_SEC]
total = (MAX_SEC or words[-1]['e']) + 0.5
frame_count = int(total * FPS)
scene.frame_start, scene.frame_end = 1, frame_count

# ── поза и движение ─────────────────────────────────────────────────────────
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='POSE')
for pb in arm.pose.bones:
    pb.rotation_mode = 'XYZ'
bpy.ops.object.mode_set(mode='OBJECT')

clips = []
for path in IDLES:
    before = {o.name for o in bpy.data.objects}
    bpy.ops.import_scene.fbx(filepath=str(path))
    added = [o for o in bpy.data.objects if o.name not in before]
    a = next((o for o in added if o.type == 'ARMATURE'), None)
    for o in added:
        if o.type == 'MESH':
            bpy.data.objects.remove(o, do_unlink=True)
    if not a:
        continue
    act = a.animation_data.action if a.animation_data else None
    lo_k, hi_k = (int(act.frame_range[0]), int(act.frame_range[1])) if act else (1, 1)
    clips.append({'arm': a, 'lo': lo_k, 'period': max(1, hi_k - lo_k), 'name': path.stem})

src_arm = clips[0]['arm'] if clips else None

if clips:
    pairs = [(src, dst) for src, dst in RETARGET.items()
             if src in src_arm.pose.bones and dst in arm.pose.bones]
    print('RETARGET: {} bones | клипы: {}'.format(
        len(pairs), ', '.join(f"{c['name']}({c['period']})" for c in clips)))

    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')

    # Ретаргет через дельту к рест-позе в мировом пространстве. Копировать
    # локальные вращения напрямую нельзя: у Mixamo и VRChat-аватара разный roll
    # костей, из-за чего руки задирало над головой.
    # Порядок обхода — от корня к листьям, иначе родитель перетрёт ребёнка.
    order = sorted(pairs, key=lambda p: len(arm.pose.bones[p[1]].parent_recursive))
    for c in clips:
        c['rest'] = {src: (c['arm'].matrix_world @ c['arm'].data.bones[src].matrix_local).to_3x3()
                     for src, _ in order if src in c['arm'].data.bones}
    rest_dst = {dst: (arm.matrix_world @ arm.data.bones[dst].matrix_local).to_3x3()
                for _, dst in order}
    arm_inv = arm.matrix_world.inverted()
    switch = max(1, int(SWITCH_SEC * FPS))
    BLEND = max(2, int(1.2 * FPS))        # длина кроссфейда между клипами
    # Случайный порядок, но без повтора подряд: seed от длины ролика,
    # чтобы один и тот же ролик пересобирался одинаково.
    random.seed(frame_count)
    order_rnd = list(range(len(clips)))
    random.shuffle(order_rnd)
    print('порядок клипов:', ', '.join(clips[i]['name'] for i in order_rnd))

    # Явный маппинг кадра вместо модификатора CYCLES: тот давал дрейф.
    # Здесь цикл точный по построению — кадр источника берётся по модулю.
    for frame in range(1, frame_count + 1):
        seg = (frame - 1) // switch
        local = (frame - 1) - seg * switch

        def sample(clip_idx, local_frame):
            """Дельты поз одного клипа на его локальном кадре."""
            c = clips[order_rnd[clip_idx % len(order_rnd)]]
            scene.frame_set(c['lo'] + (local_frame % c['period']))
            bpy.context.view_layer.update()
            res = {}
            for s_name, d_name in order:
                if s_name not in c['arm'].pose.bones:
                    continue
                pose_w = (c['arm'].matrix_world @ c['arm'].pose.bones[s_name].matrix).to_3x3()
                res[d_name] = pose_w @ c['rest'][s_name].inverted()
            return res

        deltas = sample(seg, local)

        # Плавный переход в НАЧАЛЕ отрезка: предыдущий клип продолжает играть
        # (switch + local), новый идёт с нуля, и они смешиваются. Если делать
        # наоборот — в конце отрезка — новый клип успевает проиграть первые
        # кадры и затем прыгает обратно на нулевой.
        if local < BLEND and seg > 0 and len(clips) > 1:
            t = local / BLEND
            t = t * t * (3 - 2 * t)          # smoothstep: без рывка на краях
            prev = sample(seg - 1, switch + local)
            for dst, cur_m in list(deltas.items()):
                if dst not in prev:
                    continue
                # slerp по кватернионам: линейная интерполяция матриц ведёт
                # вращение по хорде, а не по дуге — стык остаётся заметным
                deltas[dst] = prev[dst].to_quaternion().slerp(
                    cur_m.to_quaternion(), t).to_matrix()

        scene.frame_set(frame)
        for src, dst in order:
            if dst not in deltas:
                continue
            # update ДО присваивания: после него depsgraph пересчитал бы позу
            # из уже вставленных ключей и затёр бы новое значение.
            bpy.context.view_layer.update()
            pb = arm.pose.bones[dst]
            target_w = deltas[dst] @ rest_dst[dst]
            mat = (arm_inv.to_3x3() @ target_w).to_4x4()
            mat.translation = pb.matrix.translation
            pb.matrix = mat
            pb.keyframe_insert('rotation_euler', frame=frame)

    check = arm.pose.bones.get('Left arm')
    if check:
        scene.frame_set(20)
        bpy.context.view_layer.update()
        d = (arm.matrix_world @ check.tail) - (arm.matrix_world @ check.head)
        d.normalize()
        # [.., .., -1] = вниз вдоль тела; [1, .., ..] = T-поза; [.., 1, ..] = вперёд
        print('CHECK Left arm @20 dir:', [round(v, 2) for v in d])

    bpy.ops.object.mode_set(mode='OBJECT')
    for c in clips:
        bpy.data.objects.remove(c['arm'], do_unlink=True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')

# ── idle + моргание + липсинк ───────────────────────────────────────────────
meshes = [o for o in bpy.data.objects
          if o.type == 'MESH' and o.data.shape_keys
          and any(k.startswith('vrc.v_') for k in o.data.shape_keys.key_blocks.keys())]
vis_keys = {}
for m in meshes:
    kb = m.data.shape_keys.key_blocks
    for k in kb:
        if k.name.startswith('vrc.v_') or k.name.startswith('vrc.blink'):
            k.slider_max = 1.0
            vis_keys.setdefault(k.name, []).append(k)


def key_vis(name, value, frame):
    """vrc.v_e у части моделей называется vrc.v_ee — принимаем оба."""
    for candidate in (f'vrc.v_{name}', f'vrc.v_{name}{name[-1]}'):
        if candidate in vis_keys:
            for k in vis_keys[candidate]:
                k.value = value
                k.keyframe_insert('value', frame=frame)
            return


# сначала всё закрыто
for name in {k[6:] for k in vis_keys if k.startswith('vrc.v_')}:
    key_vis(name, 0.0, 1)

prev_vis = None
for w in words:
    letters = [c for c in w['t'] if c in VIS]
    if not letters:
        continue
    # согласные короче гласных — так речь читается естественнее
    weights = [1.6 if c in VOWELS else 1.0 for c in letters]
    span = max(0.06, w['e'] - w['s'])
    acc = 0.0
    scale = span / sum(weights)
    for c, weight in zip(letters, weights):
        vis = VIS[c]
        t0 = w['s'] + acc
        acc += weight * scale
        t1 = w['s'] + acc
        f0, f1 = int(t0 * FPS), int(t1 * FPS)
        if f1 <= f0:
            f1 = f0 + 1
        if prev_vis and prev_vis != vis:
            key_vis(prev_vis, 0.0, f0)
        amp = 0.95 if c in VOWELS else 0.62
        key_vis(vis, 0.0, max(1, f0 - 1))
        key_vis(vis, amp, f0 + max(1, (f1 - f0) // 2))
        key_vis(vis, 0.0, f1 + 1)
        prev_vis = vis
    # пауза между словами — рот закрыт
    gap_frame = int(w['e'] * FPS) + 2
    key_vis('sil', 0.35, gap_frame)
    key_vis('sil', 0.0, gap_frame + 3)

# моргание: случайно раз в 2.5-5.5 с, 3 кадра
blink_keys = [k for name, ks in vis_keys.items() if name.startswith('vrc.blink') for k in ks]
random.seed(7)
t = 1.2
while t < total and blink_keys:
    f = int(t * FPS)
    for k in blink_keys:
        for offset, value in ((-2, 0.0), (0, 1.0), (2, 0.0)):
            k.value = value
            k.keyframe_insert('value', frame=max(1, f + offset))
    t += random.uniform(2.5, 5.5)

# Процедурное покачивание — только если готового idle-клипа нет:
# иначе оно затрёт запечённую анимацию.
if not src_arm:
    motion = [(arm.pose.bones.get(n), a) for n, a in
              (('Head', 1.0), ('Neck', 0.6), ('Chest', 0.45), ('Spine', 0.3), ('Hips', 0.18))]
    for frame in range(1, frame_count + 1):
        tt = frame / FPS
        for pb, w8 in motion:
            if not pb:
                continue
            pb.rotation_euler[0] = (math.sin(tt * 0.9) * 0.020 + math.sin(tt * 2.3) * 0.006) * w8
            pb.rotation_euler[1] = (math.sin(tt * 0.62) * 0.028) * w8
            pb.rotation_euler[2] = (math.sin(tt * 1.13) * 0.022 + math.sin(tt * 0.41) * 0.014) * w8
            pb.keyframe_insert('rotation_euler', frame=frame)
        hips = arm.pose.bones.get('Hips')
        if hips:
            hips.location[1] = math.sin(tt * 1.05) * 0.006   # дыхание
            hips.keyframe_insert('location', frame=frame)

bpy.ops.object.mode_set(mode='OBJECT')

# ── камера: голова с плечами ────────────────────────────────────────────────
head = arm.data.bones.get('Head')
if SHOT == 'reel':
    # 9:16 целиком. ortho_scale в портретном кадре = ВЫСОТА кадра в юнитах,
    # поэтому размер считаем от головы, а центр опускаем — иначе лицо
    # встанет в середину кадра, а нужно в верхнюю треть.
    span = (head.tail_local - head.head_local).length
    head_pos = arm.matrix_world @ head.head_local
    ortho = span * 8.2
    target = Vector((head_pos.x, head_pos.y, head_pos.z - ortho * 0.20))
elif SHOT == 'waist':
    # от макушки до бёдер: лицо крупно, но движение корпуса в кадре
    hips = arm.matrix_world @ arm.data.bones['Hips'].head_local
    top = arm.matrix_world @ head.tail_local
    height = (top.z - hips.z)
    target = Vector((top.x, top.y, hips.z + height * 0.5))
    ortho = height * 1.18
elif SHOT == 'body':
    # весь габарит мешей — чтобы было видно позу рук целиком
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for m in [o for o in bpy.data.objects if o.type == 'MESH']:
        for corner in m.bound_box:
            w = m.matrix_world @ Vector(corner)
            lo = Vector((min(lo[i], w[i]) for i in range(3)))
            hi = Vector((max(hi[i], w[i]) for i in range(3)))
    target = (lo + hi) / 2
    ortho = max((hi - lo).x, (hi - lo).z) * 1.1
else:
    target = arm.matrix_world @ head.head_local
    span = (head.tail_local - head.head_local).length
    ortho = max(0.42, span * 4.6)
    target = target + Vector((0, 0, span * 0.10))

cam_data = bpy.data.cameras.new('Cam')
cam_data.type = 'ORTHO'
cam_data.ortho_scale = ortho
cam = bpy.data.objects.new('Cam', cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
cam.location = target + Vector((0, -ortho * 2.5, 0))
cam.rotation_euler = (1.5708, 0, 0)


def add_light(name, energy, offset, size):
    d = bpy.data.lights.new(name, 'AREA')
    d.energy = energy
    d.size = size
    o = bpy.data.objects.new(name, d)
    scene.collection.objects.link(o)
    o.location = target + Vector(offset)
    o.rotation_euler = (target - o.location).normalized().to_track_quat('-Z', 'Y').to_euler()


s = ortho
add_light('Key', 300 * s * s, (-s * 1.5, -s * 2.0, s * 1.3), s * 2.0)
add_light('Fill', 110 * s * s, (s * 1.9, -s * 1.5, 0), s * 2.4)
add_light('Rim', 240 * s * s, (s * 0.5, s * 2.1, s * 1.1), s * 1.6)

world = bpy.data.worlds.new('W')
scene.world = world
world.use_nodes = True
world.node_tree.nodes['Background'].inputs[0].default_value = (0.05, 0.05, 0.07, 1)
world.node_tree.nodes['Background'].inputs[1].default_value = 0.4

OUT.mkdir(parents=True, exist_ok=True)
scene.render.filepath = str(OUT / 'f_')
print(f'RENDER {frame_count} frames @ {FPS}fps -> {OUT}')
bpy.ops.render.render(animation=True)
print('DONE')

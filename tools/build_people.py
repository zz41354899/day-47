"""《他在家》人物建模腳本（Blender 4.2 以上，含 5.x）

用法：
  blender --background --python tools/build_people.py
  或在 Blender 的 Scripting 分頁打開這個檔案按 Run Script。

產出：
  src/assets/people.glb      遊戲用。三個綁好骨架的人：acheng（阿誠）、man、woman
  tools/people.blend         同一份內容的 Blender 檔，要手動修可以從這裡改

給網頁用時顧到的事：
  - 單位公尺、Z 朝上建模，匯出時轉成 glTF 的 Y 朝上；人面向 -Y（匯出後是 +Z）。
  - 每個人一張不重疊的 UV（Smart UV Project），烘一張 1024 的環境遮蔽（AO）貼圖。
  - 材質只用 Principled BSDF 的 Base Color／Roughness，顏色 × AO 貼圖，
    匯出後就是 glTF 的 baseColorFactor + baseColorTexture，three.js 可以直接換色。
  - 材質名稱固定：Skin、Shirt、Pants、Hair、Shoe、Strap、Sole、Eye、White、Lip，遊戲靠名字換顏色。
  - 骨頭名稱固定（見 BONES），每個頂點最多 4 個權重。
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
OUT_GLB = os.path.normpath(os.path.join(HERE, '..', 'src', 'assets', 'people.glb'))
OUT_BLEND = os.path.join(HERE, 'people.blend')
TEX = 1024
BAKE = '--no-bake' not in sys.argv

COLORS = {
    'Skin': (0.80, 0.56, 0.42), 'Shirt': (0.93, 0.92, 0.87), 'Pants': (0.30, 0.39, 0.44), 'Hair': (0.85, 0.84, 0.80),
    'Shoe': (0.13, 0.13, 0.13), 'Strap': (0.24, 0.42, 0.60), 'Sole': (0.93, 0.93, 0.90), 'Eye': (0.10, 0.08, 0.07), 'Lip': (0.62, 0.36, 0.32),
}
ROUGH = {'Skin': 0.6, 'Shirt': 0.9, 'Pants': 0.9, 'Hair': 0.8, 'Shoe': 0.5, 'Strap': 0.6, 'Sole': 0.7, 'Eye': 0.3, 'Lip': 0.5}
COLORS['White'] = (0.9, 0.88, 0.85); ROUGH['White'] = 0.35
MATS = list(COLORS)

# 三個人的身形與穿著。長度單位公尺。
PEOPLE = {
    # 阿誠：八十五歲，瘦一點、背比較駝，白汗衫、短褲、藍白拖。主角，面數多一級
    'acheng': dict(sh=0.172, chest=(0.150, 0.106), waist=(0.142, 0.120), hip=(0.146, 0.108), belly=0.022, stoop=0.042, limb=0.92,
                   sleeve=0.5, forearm_sleeve=0, pants=0.52, long=False, shoes=False, hair='thin', female=False, sub=2),
    # 一般男性：襯衫、長褲、鞋子
    'man': dict(sh=0.192, chest=(0.168, 0.108), waist=(0.146, 0.106), hip=(0.148, 0.104), belly=0.01, stoop=0.006, limb=1.06,
                sleeve=1.0, forearm_sleeve=0.9, pants=1.0, long=True, shoes=True, hair='short', female=False, sub=1),
    # 一般女性：肩膀窄一點、髖寬一點，燙過的短髮
    'woman': dict(sh=0.166, chest=(0.144, 0.104), waist=(0.126, 0.096), hip=(0.158, 0.112), belly=0.006, stoop=0.008, limb=0.94,
                  sleeve=1.0, forearm_sleeve=0.9, pants=1.0, long=True, shoes=True, hair='perm', female=True, sub=1),
}

g = lambda v, c, s: math.exp(-((v - c) / s) ** 2)
smooth = lambda a, b, v: max(0.0, min(1.0, (v - a) / (b - a))) ** 2 * (3 - 2 * max(0.0, min(1.0, (v - a) / (b - a))))


def joints(P):
    """骨架的關節位置（也是皮膚的中心線）。手臂是張開 15 度的 A 字。"""
    sh = P['sh']
    J = {
        'hips': Vector((0, 0, 0.88)), 'spine': Vector((0, -P['belly'] * 0.4, 1.02)), 'chest': Vector((0, P['stoop'] * 0.5, 1.17)),
        'upper': Vector((0, P['stoop'], 1.31)), 'neck': Vector((0, P['stoop'] * 0.8, 1.385)), 'head': Vector((0, P['stoop'] * 0.2 - 0.004, 1.455)),
        'top': Vector((0, P['stoop'] * 0.2 - 0.008, 1.66)),
    }
    for s, k in ((1, 'L'), (-1, 'R')):
        J['shoulder.' + k] = Vector((s * sh, P['stoop'] * 0.9, 1.352))
        J['elbow.' + k] = Vector((s * (sh + 0.068), P['stoop'] * 0.9 + 0.008, 1.088))
        J['wrist.' + k] = Vector((s * (sh + 0.128), P['stoop'] * 0.9 - 0.02, 0.858))
        J['tip.' + k] = Vector((s * (sh + 0.158), P['stoop'] * 0.9 - 0.038, 0.69))
        J['hip.' + k] = Vector((s * 0.088, 0, 0.84))
        J['knee.' + k] = Vector((s * 0.092, -0.006, 0.47))
        J['ankle.' + k] = Vector((s * 0.092, 0.014, 0.082))
        J['toe.' + k] = Vector((s * 0.1, -0.165, 0.028))
    return J


# 骨頭：名字 → (頭, 尾, 父骨)
def bones(J):
    B = {
        'Hips': ('hips', 'spine', None), 'Spine': ('spine', 'chest', 'Hips'), 'Chest': ('chest', 'neck', 'Spine'),
        'Neck': ('neck', 'head', 'Chest'), 'Head': ('head', 'top', 'Neck'),
    }
    for k in 'LR':
        B['UpperArm.' + k] = ('shoulder.' + k, 'elbow.' + k, 'Chest')
        B['ForeArm.' + k] = ('elbow.' + k, 'wrist.' + k, 'UpperArm.' + k)
        B['Hand.' + k] = ('wrist.' + k, 'tip.' + k, 'ForeArm.' + k)
        B['Thigh.' + k] = ('hip.' + k, 'knee.' + k, 'Hips')
        B['Shin.' + k] = ('knee.' + k, 'ankle.' + k, 'Thigh.' + k)
        B['Foot.' + k] = ('ankle.' + k, 'toe.' + k, 'Shin.' + k)
    return B


def skin_body(P, J, swap=False):
    """沿著骨架長出一層皮：Skin 修改器 + 細分。回傳已套用的 mesh。"""
    R = lambda rx, ry: (ry, rx) if swap else (rx, ry)
    pts, edges, rad = [], [], []

    def v(co, r):
        pts.append(Vector(co)); rad.append(r if isinstance(r, tuple) else (r, r)); return len(pts) - 1

    def chain(start, items):
        prev = start
        for co, r in items:
            i = v(co, r); edges.append((prev, i)); prev = i
        return prev

    L = P['limb']
    root = v(J['hips'], R(*P['hip']))
    w = v(J['spine'], R(P['waist'][0], P['waist'][1]))
    c = v(J['chest'], R(*P['chest']))
    u = v(J['upper'] + Vector((0, 0, 0.02)), R(P['sh'] * 0.9, 0.092))
    edges.extend([(root, w), (w, c), (c, u)])
    chain(u, [(J['neck'], 0.058), (J['head'], 0.05)])
    for s, k in ((1, 'L'), (-1, 'R')):
        a, e, wr, tip = J['shoulder.' + k], J['elbow.' + k], J['wrist.' + k], J['tip.' + k]
        chain(u, [(a, 0.058 * L), ((a + e) / 2, 0.052 * L), (e, 0.043 * L), (e.lerp(wr, 0.4), 0.042 * L), (wr, 0.031 * L),
                  (wr.lerp(tip, 0.45), 0.034), (tip, 0.026)])
        h, kn, an, toe = J['hip.' + k], J['knee.' + k], J['ankle.' + k], J['toe.' + k]
        chain(root, [(h, 0.1 * L), ((h + kn) / 2, 0.084 * L), (kn, 0.06 * L), (kn.lerp(an, 0.35) + Vector((0, 0.014, 0)), 0.06 * L), (an, 0.042),
                     (Vector((an.x, an.y - 0.035, 0.045)), (0.046, 0.038)), (toe, (0.046, 0.024))])
    me = bpy.data.meshes.new('skin')
    bm = bmesh.new()
    layer = bm.verts.layers.skin.verify()
    bv = [bm.verts.new(p) for p in pts]
    for a, b in edges:
        bm.edges.new((bv[a], bv[b]))
    for i, vert in enumerate(bv):
        vert[layer].radius = rad[i]
        vert[layer].use_root = i == root
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new('skin', me)
    bpy.context.collection.objects.link(ob)
    ob.modifiers.new('Skin', 'SKIN')
    sub = ob.modifiers.new('Sub', 'SUBSURF'); sub.levels = P.get('sub', 1)
    out = bpy.data.meshes.new_from_object(ob.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    bpy.data.objects.remove(ob); bpy.data.meshes.remove(me)
    return out


def head_bm(P, J):
    """頭：一顆細分過的球，捏出下顎、鼻子、眉骨、眼窩、顴骨、嘴唇、下巴。臉朝 -Y。"""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=40, radius=1.0)
    c = Vector((0, J['top'].y - 0.004, 1.548))
    fem = P['female']
    for v in bm.verts:
        d = v.co.normalized()
        X, Y, Z = d.x * 0.077, d.y * 0.097, d.z * 0.113
        t = max(0.0, -d.z)
        X *= 1 - (0.24 if not fem else 0.3) * smooth(0.2, 1.0, t)  # 臉頰往下顎收，但留著下顎的寬度
        if d.y > 0: Y *= 1 - 0.34 * t ** 1.4                        # 後腦往脖子收
        Z *= 1 - 0.06 * smooth(0.5, 1.0, t)
        f = smooth(0.1, 0.7, -d.y)                                  # 只動臉這一面
        ax = abs(X)
        Y -= f * 0.028 * g(X, 0, 0.0105) * g(Z, -0.016, 0.024)      # 鼻樑到鼻頭
        Y -= f * 0.008 * g(X, 0, 0.0165) * g(Z, -0.031, 0.0085)     # 鼻頭、鼻翼
        Y -= f * 0.008 * g(Z, 0.036, 0.011) * (0.55 + 0.45 * g(ax, 0.03, 0.022))  # 眉骨
        Y += f * 0.0095 * g(ax, 0.031, 0.0125) * g(Z, 0.015, 0.0095)  # 眼窩
        Y -= f * 0.005 * g(ax, 0.049, 0.017) * g(Z, -0.012, 0.018)  # 顴骨
        Y += f * 0.004 * g(ax, 0.036, 0.012) * g(Z, -0.05, 0.02)    # 嘴角兩側凹下去
        Y -= f * 0.0065 * g(X, 0, 0.021) * g(Z, -0.056, 0.0075)     # 嘴唇
        Y += f * 0.003 * g(X, 0, 0.02) * g(Z, -0.071, 0.006)        # 唇下
        Y -= f * 0.010 * g(X, 0, 0.022) * g(Z, -0.091, 0.016)       # 下巴
        v.co = c + Vector((X, Y, Z))
    return bm, c


def ellipsoid(bm, co, r, mat, seg=10):
    geo = bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=max(6, seg // 2 + 2), radius=1.0)
    for v in geo['verts']:
        v.co = Vector(co) + Vector((v.co.x * r[0], v.co.y * r[1], v.co.z * r[2]))
    for f in {f for v in geo['verts'] for f in v.link_faces}:
        f.material_index = MATS.index(mat)
    return geo['verts']


def box(bm, co, size, mat):
    geo = bmesh.ops.create_cube(bm, size=1.0)
    for v in geo['verts']:
        v.co = Vector(co) + Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    for f in {f for v in geo['verts'] for f in v.link_faces}:
        f.material_index = MATS.index(mat)
    return geo['verts']


def seg_t(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
    return t, (p - (a + ab * t)).length


def build(name, P):
    J = joints(P)
    B = bones(J)
    # 1. 身體
    me = skin_body(P, J)
    xs = [v.co.x for v in me.vertices if 1.1 < v.co.z < 1.25 and abs(v.co.x) < P['sh'] - 0.02]
    ys = [v.co.y for v in me.vertices if 1.1 < v.co.z < 1.25 and abs(v.co.x) < P['sh'] - 0.02]
    if xs and (max(ys) - min(ys)) > (max(xs) - min(xs)):  # Skin 修改器把寬和厚弄反了，換過來重做
        bpy.data.meshes.remove(me)
        me = skin_body(P, J, swap=True)
    bm = bmesh.new(); bm.from_mesh(me); bpy.data.meshes.remove(me)
    zfix = 0.0
    # 手掌：Skin 修改器長出來的是圓棒，這裡壓扁成手掌的厚度（掌心朝大腿）
    for k in 'LR':
        wr, tip = J['wrist.' + k], J['tip.' + k]
        axis = (tip - wr).normalized()
        thick = axis.cross(Vector((0, 1, 0))).normalized()
        for v in bm.verts:
            t = (v.co - wr).dot(axis) / (tip - wr).length
            if t < -0.15 or (v.co - wr).length > 0.26 or (v.co.x > 0) != (wr.x > 0): continue
            wgt = smooth(-0.15, 0.3, t)
            off = v.co - (wr + axis * (v.co - wr).dot(axis))
            if off.length > 0.06: continue  # 只動手，不要動到旁邊的大腿
            a, b = off.dot(thick), off.dot(Vector((0, 1, 0)))
            v.co += thick * a * (0.5 - 1) * wgt + Vector((0, 1, 0)) * b * (1.3 - 1) * wgt
    # 先只拿身體去綁骨架（自動權重要看得到表面才算得出來，蓋了衣服就會失敗）
    for f in bm.faces: f.smooth = True
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh); bm.free()
    ob = bpy.data.objects.new(name + '_mesh', mesh)
    bpy.context.collection.objects.link(ob)
    rig = make_rig(name, B, J)
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True); rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    try:
        bpy.ops.object.parent_set(type='ARMATURE_AUTO')
    except Exception as e:
        print('自動權重失敗，改用包絡：', e)
        bpy.ops.object.parent_set(type='ARMATURE_ENVELOPE')
    for bn in B:
        if bn not in ob.vertex_groups: ob.vertex_groups.new(name=bn)
    # 沒算到權重的頂點，交給最近的骨頭
    for v in mesh.vertices:
        if not v.groups:
            best, bd = None, 9
            for bn, (a, b, _) in B.items():
                t, d = seg_t(v.co, J[a], J[b])
                if d < bd: best, bd = bn, d
            ob.vertex_groups[best].add([v.index], 1.0, 'REPLACE')
    GI = {vg.name: vg.index for vg in ob.vertex_groups}
    bm = bmesh.new(); bm.from_mesh(mesh)
    dl = bm.verts.layers.deform.verify()
    part = bm.faces.layers.int.new('part')      # 0 身體　1 頭　2 配件（鞋底、眼睛…）　3 衣服
    rigid = bm.verts.layers.int.new('rigid')    # 1 整個跟著頭　2 左腳　3 右腳
    for f in bm.faces:
        f.material_index = MATS.index('Skin')

    # 2. 頭、耳朵、五官
    hb, hc = head_bm(P, J)
    tree = BVHTree.FromBMesh(hb)
    surf = lambda x, z: tree.ray_cast(hc + Vector((x, -0.5, z)), Vector((0, 1, 0)))[0]
    tmp = bpy.data.meshes.new('head'); hb.to_mesh(tmp); hb.free()
    n0 = len(bm.verts); f0 = len(bm.faces)
    bm.from_mesh(tmp); bpy.data.meshes.remove(tmp)
    bm.verts.ensure_lookup_table(); bm.faces.ensure_lookup_table()
    for f in bm.faces[f0:]:
        f[part] = 1; f.material_index = MATS.index('Skin')
    head_verts = list(bm.verts[n0:])
    extra = []
    for s in (1, -1):
        extra += ellipsoid(bm, hc + Vector((s * 0.0755, 0.014, -0.004)), (0.008, 0.017, 0.03), 'Skin')
        p = surf(s * 0.031, 0.015)
        extra += ellipsoid(bm, p + Vector((0, 0.004, 0)), (0.0125, 0.006, 0.0058), 'White', 10)
        extra += ellipsoid(bm, p + Vector((0, 0.0005, -0.0004)), (0.0052, 0.004, 0.0052), 'Eye', 8)
        extra += ellipsoid(bm, p + Vector((0, 0.002, 0.0052)), (0.0145, 0.0062, 0.0042), 'Skin', 10)  # 上眼皮
        p = surf(s * 0.033, 0.036)
        extra += ellipsoid(bm, p + Vector((0, 0.002, 0.001)), (0.017, 0.0042, 0.0034), 'Hair', 8)
    p = surf(0, -0.056)
    extra += ellipsoid(bm, p + Vector((0, 0.003, 0)), (0.02, 0.004, 0.0038), 'Lip', 8)
    for v in head_verts + extra:
        v[rigid] = 1
    for f in {f for v in extra for f in v.link_faces}:
        f[part] = 2

    # 3. 頭髮：把頭皮那一片往外推一層
    style = P['hair']
    bm.faces.ensure_lookup_table()
    def hairy(f):
        h = f.calc_center_median() - hc
        if style == 'thin':  # 頭頂禿了，剩後腦和耳朵上面一圈
            return h.y > -0.03 and -0.05 < h.z < 0.068 and (h.z > 0.03 or h.y > 0.034)
        if style == 'short': return h.z + 0.84 * h.y > 0.002 and (h.z > 0.024 or h.y > 0.03)
        return h.z + 0.84 * h.y > 0.004 and (h.z > 0.026 or h.y > 0.03)  # perm
    push = {'thin': 0.005, 'short': 0.009, 'perm': 0.02}[style]
    sel = [f for f in bm.faces if f[part] == 1 and hairy(f)]
    dup = bmesh.ops.duplicate(bm, geom=sel)
    hv = [e for e in dup['geom'] if isinstance(e, bmesh.types.BMVert)]
    for v in hv:
        h = v.co - hc
        k = push * (1.0 + (0.35 * math.sin(h.x * 190) * math.sin(h.z * 170 + h.y * 150) if style == 'perm' else 0.0))
        v.co += (h.normalized() if h.length else Vector((0, 0, 1))) * k
        v[rigid] = 1
    for f in [e for e in dup['geom'] if isinstance(e, bmesh.types.BMFace)]:
        f.material_index = MATS.index('Hair'); f[part] = 2

    # 4. 衣服：照最近的骨頭分區，複製一層往外推
    def region(f):
        p = f.calc_center_median()
        best, bt, bd = None, 0, 9
        for bn, (a, b, _) in B.items():
            t, d = seg_t(p, J[a], J[b])
            if d < bd: best, bt, bd = bn, t, d
        # 腋下那一帶離手臂的骨頭比較近，但其實是身體
        if best.split('.')[0] in ('UpperArm', 'ForeArm', 'Hand') and bd > 0.056 * P['limb']:
            best, bt, bd = None, 0, 9
            for bn, (a, b, _) in B.items():
                if bn.split('.')[0] in ('UpperArm', 'ForeArm', 'Hand'): continue
                t, d = seg_t(p, J[a], J[b])
                if d < bd: best, bt, bd = bn, t, d
        return best, bt, p
    def cut(pred, co, no):
        fs = [f for f in bm.faces if f[part] == 0 and pred(*region(f))]
        geom = list({e for f in fs for e in f.edges}) + list({v for f in fs for v in f.verts}) + fs
        if geom: bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=no, dist=0.0005)
    torso = lambda bn, t, p: bn.split('.')[0] in ('Hips', 'Spine', 'Chest', 'Neck', 'Thigh')
    HEM, BELT = 0.895 - zfix, 0.96 - zfix
    COLLAR = Vector((0, J['neck'].y, 1.43 - zfix)); COLLAR_N = Vector((0, -0.32, 1)).normalized()
    cut(torso, Vector((0, 0, HEM)), Vector((0, 0, 1)))
    cut(torso, Vector((0, 0, BELT)), Vector((0, 0, 1)))
    cut(lambda bn, t, p: bn.split('.')[0] in ('Chest', 'Neck', 'Head'), COLLAR, COLLAR_N)
    for k in 'LR':
        def limb_cut(a, b, t):
            A, Bv = J[a + '.' + k], J[b + '.' + k]
            co = A.lerp(Bv, t)
            cut(lambda bn, tt, p: (p - co).length < 0.16 and bn.endswith(k), co, (Bv - A).normalized())
        if P['sleeve'] < 1: limb_cut('shoulder', 'elbow', P['sleeve'])
        if 0 < P['forearm_sleeve'] < 1: limb_cut('elbow', 'wrist', P['forearm_sleeve'])
        if P['pants'] < 1: limb_cut('hip', 'knee', P['pants'])
        if P['long']: limb_cut('knee', 'ankle', 0.9)
        if not P['shoes']:
            for y in (-0.125, -0.075):
                cut(lambda bn, t, p: bn == 'Foot.' + k, Vector((0, y, 0)), Vector((0, 1, 0)))
    bm.faces.ensure_lookup_table()
    shirt, pants, shoe, strap = [], [], [], []
    for f in bm.faces:
        if f[part] != 0: continue
        bn, t, p = region(f)
        base = bn.split('.')[0]
        body = base in ('Hips', 'Spine', 'Chest', 'Neck', 'Thigh')
        if body and p.z > HEM and (p - COLLAR).dot(COLLAR_N) < 0: shirt.append(f)
        elif base == 'UpperArm' and t < P['sleeve']: shirt.append(f)
        elif base == 'ForeArm' and t < P['forearm_sleeve']: shirt.append(f)
        if body and p.z < BELT and (base != 'Thigh' or t < P['pants'] or p.z > J['hip.L'].z - zfix): pants.append(f)
        elif base == 'Shin' and P['long'] and t < 0.9: pants.append(f)
        if P['shoes'] and (base == 'Foot' or (base == 'Shin' and t > 0.88)): shoe.append(f)
        if not P['shoes'] and base == 'Foot' and -0.125 < p.y < -0.075: strap.append(f)
    def shell(faces, mat, off):
        if not faces: return
        d = bmesh.ops.duplicate(bm, geom=faces)
        for v in [e for e in d['geom'] if isinstance(e, bmesh.types.BMVert)]:
            v.co += v.normal * off
        for f in [e for e in d['geom'] if isinstance(e, bmesh.types.BMFace)]:
            f.material_index = MATS.index(mat); f[part] = 3
    bm.normal_update()
    shell(pants, 'Pants', 0.007)
    shell(shirt, 'Shirt', 0.011)
    shell(shoe, 'Shoe', 0.009)
    shell(strap, 'Strap', 0.005)
    # 藍白拖的鞋底／鞋子的鞋底
    for s, k, tag in ((1, 'L', 2), (-1, 'R', 3)):
        an = J['ankle.' + k]
        sole = box(bm, (an.x + s * 0.004, -0.062, 0.006 if P['shoes'] else 0.008), (0.098, 0.262, 0.012 if P['shoes'] else 0.016), 'Shoe' if P['shoes'] else 'Sole')
        for v in sole: v[rigid] = tag
        for f in {f for v in sole for f in v.link_faces}: f[part] = 2

    # 頭、五官、頭髮、鞋底不變形：整塊跟著一根骨頭
    fixed = {1: 'Head', 2: 'Foot.L', 3: 'Foot.R'}
    for v in bm.verts:
        if v[rigid]:
            v[dl].clear()
            v[dl][GI[fixed[v[rigid]]]] = 1.0
    for f in bm.faces: f.smooth = True
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    for m in MATS: mesh.materials.append(make_mat(name, m))
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True); bpy.context.view_layer.objects.active = ob
    bpy.ops.object.vertex_group_limit_total(group_select_mode='ALL', limit=4)
    bpy.ops.object.vertex_group_normalize_all(group_select_mode='ALL', lock_active=False)

    # UV：一張不重疊的圖
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(78), island_margin=0.006)
    bpy.ops.object.mode_set(mode='OBJECT')
    return rig, ob


def make_rig(name, B, J):
    arm = bpy.data.armatures.new(name + '_rig')
    rig = bpy.data.objects.new(name, arm)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    eb = {}
    for bn, (a, b, parent) in B.items():
        e = arm.edit_bones.new(bn)
        e.head = J[a]; e.tail = J[b]
        eb[bn] = e
    for bn, (a, b, parent) in B.items():
        if parent: eb[bn].parent = eb[parent]
    bpy.ops.object.mode_set(mode='OBJECT')
    return rig


def make_mat(name, m):
    mat = bpy.data.materials.new(name + '.' + m)
    mat.use_nodes = True
    mat.use_backface_culling = m not in ('Shirt', 'Pants', 'Hair', 'Strap')  # 衣服和頭髮是單層的殼，兩面都要畫
    bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Base Color'].default_value = (*COLORS[m], 1)
    bsdf.inputs['Roughness'].default_value = ROUGH[m]
    bsdf.inputs['Metallic'].default_value = 0
    return mat


def bake_ao(name, ob):
    """烘 AO 到一張圖，接成 顏色 × AO。"""
    img = bpy.data.images.new(name + '_ao', TEX, TEX)
    for mat in ob.data.materials:
        nt = mat.node_tree
        tex = nt.nodes.new('ShaderNodeTexImage'); tex.image = img; tex.name = 'AO'
        nt.nodes.active = tex
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 48
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True); bpy.context.view_layer.objects.active = ob
    if sc.world is None: sc.world = bpy.data.worlds.new('World')
    sc.world.light_settings.distance = 0.3   # 只算近處的遮蔽：腋下、領口、褲管
    bpy.ops.object.bake(type='AO', margin=8)
    # AO 只拿來加一點明暗，不能有全黑的地方（被衣服蓋住的皮膚、沒烘到的邊）
    import numpy as np
    px = np.empty(TEX * TEX * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(-1, 4)
    px[:, :3] = 0.5 + 0.5 * np.clip(px[:, :3], 0, 1) ** 0.8
    px[:, 3] = 1
    img.pixels.foreach_set(px.ravel())
    img.pack()
    for mat in ob.data.materials:
        nt = mat.node_tree
        bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
        tex = nt.nodes['AO']
        mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
        mix.inputs[0].default_value = 1.0
        mix.inputs[6].default_value = bsdf.inputs['Base Color'].default_value
        nt.links.new(tex.outputs['Color'], mix.inputs[7])
        nt.links.new(mix.outputs[2], bsdf.inputs['Base Color'])


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    rigs = []
    for name, P in PEOPLE.items():
        rig, ob = build(name, P)
        if BAKE:
            try: bake_ao(name, ob)
            except Exception as e: print('AO 烘焙失敗，改用純色：', e)
        rig.location.x = 10 + len(rigs) * 2  # 先移開，免得擋到下一個人的烘焙
        bpy.context.view_layer.update()
        rigs.append(rig)
        print(name, 'verts', len(ob.data.vertices), 'tris', sum(len(p.vertices) - 2 for p in ob.data.polygons))
    for i, rig in enumerate(rigs): rig.location.x = i * 0.8
    os.makedirs(os.path.dirname(OUT_GLB), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
    for o in bpy.data.objects:
        if o.type == 'ARMATURE': o.location.x = 0   # 匯出時每個人都站在原點
    bpy.ops.export_scene.gltf(filepath=OUT_GLB, export_format='GLB', export_yup=True, export_skins=True, export_animations=False,
                              export_image_format='JPEG', export_jpeg_quality=82, export_all_influences=False)
    print('wrote', OUT_GLB, os.path.getsize(OUT_GLB) // 1024, 'KB')


main()

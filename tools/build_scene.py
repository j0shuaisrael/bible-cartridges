#!/usr/bin/env python3
"""Build the canonical PSLM v4 scene part (tools/scene.json).

The scene part is a standard glTF 2.0 scene document (key "gltf") plus
plain-data sections for the things glTF core does not name:

  gltf         -- Khronos glTF 2.0: scroll meshes (box + cylinders),
                  perspective camera, sun as KHR_lights_punctual,
                  palace referenced by the PSLM_part extension.
  sky          -- plain data: the panorama from the skybox part, used as
                  the scene background AND as the image-based lighting
                  environment (ambient + reflections). glTF core has no
                  scene background and no scene environment.
  scroll_text  -- plain data: layout for generating the dynamic scroll
                  texture (named "scroll-text") from the text part.
  animation    -- plain data: the scroll bob, as a formula (glTF
                  animations are keyframed; a sine is exact as a formula).
  controls     -- plain data: interaction, not scene.
  audio        -- plain data: which part holds the audio, and its MIME type.
  renderer     -- plain data: renderer settings (antialias, tone mapping,
                  exposure, output colour space, pixel-ratio cap).

Values are taken from decode.html's startWorld (the reference
implementation). Colours in the glTF are LINEAR (glTF baseColorFactor is
linear); colours in the plain-data sections are sRGB hex strings.

Gaps worked around (all flagged in the spec, none hidden):
  * Hemisphere light is not in glTF. The ambient contribution comes from
    image-based lighting from the sky environment (sky.environment), and
    the sun is a KHR_lights_punctual directional light. The old neutral
    studio-room environment (RoomEnvironment) and its prefilter blur are
    gone: the world is now fully contained in the cartridge.
  * Sky background is not in glTF core. The skybox GLB contains a sphere
    mesh (radius ~50000) with the panorama as its emissive texture, but
    that sphere is NOT rendered as a node: its radius exceeds the camera
    far plane (500), and the panorama is used directly as the equirect
    background/environment instead (the standard approach the spec
    names). The skybox part is referenced by the sky section, which
    extracts the panorama texture from it.
  * The scroll-text texture is dynamic (chapter + language). The scene
    references it by the plain name "scroll-text" (the image uri in the
    glTF), and the scroll_text section carries the layout data the
    renderer uses to generate it.
  * The bundled three.js in decode.html does not implement
    KHR_lights_punctual, so our decoder reads that extension from the
    glTF JSON directly and creates the light; a loader that supports the
    extension creates it natively. The sun node carries a lookAt rotation
    so its -Z axis points from its position toward the origin.

Run: python3 tools/build_scene.py   (writes tools/scene.json)
"""
import base64
import json
import math
import struct
import sys
from pathlib import Path

# ---------------------------------------------------------------- values
# (from decode.html startWorld; the reference implementation)

SHEET_W, SHEET_H, SHEET_D = 7.0, 3.5, 0.06
SHEET_Z = -0.3
ROLL_R, ROLL_LEN, ROLL_SEG = 0.5, 3.5, 24
ROD_R, ROD_LEN, ROD_SEG = 0.07, 4.3, 12
CAP_R, CAP_H, CAP_SEG = 0.56, 0.12, 24
ROLL_X = SHEET_W / 2 + 0.3          # 3.8
CAP_Y = 1.81
SCROLL_POS = [0.0, 3.6, 0.0]

COLORS = {
    "sheet_edge": "#b08d55",
    "roll": "#c8a06a",
    "wood": "#7a5230",
    "palace_metal": "#f2f3f5",
    "sun": "#fff2dd",
}


def srgb_to_linear(hex_color):
    """'#rrggbb' (sRGB) -> [r, g, b] linear, as glTF baseColorFactor."""
    h = hex_color.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return [round(v, 6) for v in out]


def quat_axis_angle(axis, angle):
    x, y, z = axis
    s = math.sin(angle / 2.0)
    return [round(x * s, 9), round(y * s, 9), round(z * s, 9), round(math.cos(angle / 2.0), 9)]


def quat_from_matrix(m):
    """Rotation matrix (3 rows of 3, column-major basis vectors) -> [x, y, z, w]."""
    (m00, m01, m02), (m10, m11, m12), (m20, m21, m22) = m
    tr = m00 + m11 + m22
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        w, x, y, z = 0.25 * s, (m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2
        w, x, y, z = (m21 - m12) / s, 0.25 * s, (m01 + m10) / s, (m02 + m20) / s
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2
        w, x, y, z = (m02 - m20) / s, (m01 + m10) / s, 0.25 * s, (m12 + m21) / s
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2
        w, x, y, z = (m10 - m01) / s, (m02 + m20) / s, (m12 + m21) / s, 0.25 * s
    return [round(x, 9), round(y, 9), round(z, 9), round(w, 9)]


def look_at_quat(eye, target, up=(0.0, 1.0, 0.0)):
    """Quaternion whose -Z axis points from eye toward target (glTF node)."""
    def sub(a, b):
        return [a[i] - b[i] for i in range(3)]
    def cross(a, b):
        return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
                a[0] * b[1] - a[1] * b[0]]
    def norm(a):
        l = math.sqrt(sum(v * v for v in a))
        return [v / l for v in a]
    z = norm(sub(eye, target))          # node +Z points away from target
    x = norm(cross(up, z))
    y = cross(z, x)
    # rotation matrix rows: (x_axis, y_axis, z_axis) as columns
    return quat_from_matrix([[x[0], y[0], z[0]],
                             [x[1], y[1], z[1]],
                             [x[2], y[2], z[2]]])


# ---------------------------------------------------------------- geometry
# Each mesh is built as (positions, normals, uvs, indices) with correct
# outward winding (counter-clockwise seen from outside the surface).

def box_faces(hx, hy, hz):
    """Six faces; each face is 4 corners (CCW from outside) with u,v 0..1.
    Returns a list of (normal, [4 (x,y,z)], [(u,v) x 4])."""
    faces = []
    # (normal, u-axis, v-axis, centre) with u x v == normal
    defs = [
        ((1, 0, 0), (0, 0, -1), (0, 1, 0), (hx, 0, 0)),     # +X
        ((-1, 0, 0), (0, 0, 1), (0, 1, 0), (-hx, 0, 0)),    # -X
        ((0, 1, 0), (1, 0, 0), (0, 0, -1), (0, hy, 0)),     # +Y
        ((0, -1, 0), (1, 0, 0), (0, 0, 1), (0, -hy, 0)),    # -Y
        ((0, 0, 1), (1, 0, 0), (0, 1, 0), (0, 0, hz)),      # +Z (front)
        ((0, 0, -1), (-1, 0, 0), (0, 1, 0), (0, 0, -hz)),   # -Z
    ]
    for n, u, v, c in defs:
        corners, uvs = [], []
        # glTF convention: v=0 is the TOP of the image (textures are not
        # flipped). The corners are ordered bottom-left, bottom-right,
        # top-right, top-left in 3D, so their v runs 1, 1, 0, 0.
        for su, sv, uu, vv in ((-1, -1, 0, 1), (1, -1, 1, 1), (1, 1, 1, 0), (-1, 1, 0, 0)):
            p = [c[0], c[1], c[2]]
            for i in range(3):
                p[i] += su * u[i] * (hx if i == 0 else hy if i == 1 else hz)
                p[i] += sv * v[i] * (hx if i == 0 else hy if i == 1 else hz)
            corners.append(tuple(p))
            uvs.append((uu, vv))
        faces.append((n, corners, uvs))
    return faces


def box_mesh(hx, hy, hz):
    """One primitive per face (so each face can carry its own material).
    Returns (primitives, verts, indices) where primitives is a list of
    (face_index, [vertex indices]) and verts are (pos, normal, uv)."""
    verts, prims = [], []
    for fi, (n, corners, uvs) in enumerate(box_faces(hx, hy, hz)):
        base = len(verts)
        for (x, y, z), (u, v) in zip(corners, uvs):
            verts.append(((x, y, z), n, (u, v)))
        prims.append((fi, [base, base + 1, base + 2, base, base + 2, base + 3]))
    return verts, prims


def cylinder_mesh(radius, height, segments):
    """Capped cylinder along Y, centred at the origin.
    Returns (verts, indices)."""
    verts, idx = [], []
    h2 = height / 2.0
    # side: (segments+1) x 2 vertices (top row, bottom row).
    # glTF convention: v=0 is the top of the image.
    for i in range(segments + 1):
        th = 2.0 * math.pi * i / segments
        sx, sz = math.sin(th), math.cos(th)
        u = i / segments
        verts.append(((radius * sx, h2, radius * sz), (sx, 0.0, sz), (u, 0.0)))
        verts.append(((radius * sx, -h2, radius * sz), (sx, 0.0, sz), (u, 1.0)))
    for i in range(segments):
        t0, b0 = 2 * i, 2 * i + 1
        t1, b1 = 2 * i + 2, 2 * i + 3
        idx += [t0, b0, t1, t1, b0, b1]
    # caps: centre + ring, planar UVs
    for y, normal, flip in ((h2, (0.0, 1.0, 0.0), False),
                            (-h2, (0.0, -1.0, 0.0), True)):
        base = len(verts)
        verts.append(((0.0, y, 0.0), normal, (0.5, 0.5)))
        for i in range(segments + 1):
            th = 2.0 * math.pi * i / segments
            sx, sz = math.sin(th), math.cos(th)
            verts.append(((radius * sx, y, radius * sz), normal,
                          (0.5 + sx / 2.0, 0.5 - sz / 2.0)))
        for i in range(segments):
            a, b = base + 1 + i, base + 1 + i + 1
            idx += [base, b, a] if flip else [base, a, b]
    return verts, idx


# ---------------------------------------------------------------- glTF build
class GltfBuilder:
    def __init__(self):
        self.buf = bytearray()
        self.buffer_views = []
        self.accessors = []
        self.meshes = []

    def _align4(self):
        while len(self.buf) % 4:
            self.buf.append(0)

    def add_accessor(self, data_bytes, component_type, type_, count, minmax=None):
        self._align4()
        off = len(self.buf)
        self.buf += data_bytes
        bv = len(self.buffer_views)
        self.buffer_views.append({"buffer": 0, "byteOffset": off,
                                  "byteLength": len(data_bytes)})
        acc = {"bufferView": bv, "componentType": component_type,
               "count": count, "type": type_}
        if minmax is not None:
            acc["min"], acc["max"] = minmax
        self.accessors.append(acc)
        return len(self.accessors) - 1

    def add_mesh(self, name, verts, prims):
        """verts: list of ((x,y,z), (nx,ny,nz), (u,v)).
        prims: list of (material_index, [indices])."""
        pos = [v[0] for v in verts]
        nor = [v[1] for v in verts]
        uv = [v[2] for v in verts]
        pos_b = b"".join(struct.pack("<3f", *p) for p in pos)
        nor_b = b"".join(struct.pack("<3f", *p) for p in nor)
        uv_b = b"".join(struct.pack("<2f", *p) for p in uv)
        mins = [min(p[i] for p in pos) for i in range(3)]
        maxs = [max(p[i] for p in pos) for i in range(3)]
        a_pos = self.add_accessor(pos_b, 5126, "VEC3", len(pos), (mins, maxs))
        a_nor = self.add_accessor(nor_b, 5126, "VEC3", len(nor))
        a_uv = self.add_accessor(uv_b, 5126, "VEC2", len(uv))
        # Each primitive gets its OWN index accessor: glTF has no index
        # offset, so primitives cannot share one accessor over a range.
        primitives = []
        for mat, inds in prims:
            ib = b"".join(struct.pack("<I", i) for i in inds)
            ai = self.add_accessor(ib, 5125, "SCALAR", len(inds))
            primitives.append({
                "attributes": {"POSITION": a_pos, "NORMAL": a_nor,
                               "TEXCOORD_0": a_uv},
                "indices": ai, "material": mat})
        self.meshes.append({"name": name, "primitives": primitives})
        return len(self.meshes) - 1


def build_scene():
    b = GltfBuilder()

    # --- sheet: 6 primitives (one per face), front (+Z, face 4) textured
    sheet_verts, sheet_prims = box_mesh(SHEET_W / 2, SHEET_H / 2, SHEET_D / 2)
    # material per face: edge, edge, edge, edge, scroll-text, edge
    face_mats = [0, 0, 0, 0, 1, 0]
    prims = [(face_mats[fi], inds) for fi, inds in sheet_prims]
    sheet = b.add_mesh("scroll-sheet", sheet_verts, prims)

    roll_verts, roll_idx = cylinder_mesh(ROLL_R, ROLL_LEN, ROLL_SEG)
    roll = b.add_mesh("scroll-roll", roll_verts, [(2, roll_idx)])
    rod_verts, rod_idx = cylinder_mesh(ROD_R, ROD_LEN, ROD_SEG)
    rod = b.add_mesh("scroll-rod", rod_verts, [(3, rod_idx)])
    cap_verts, cap_idx = cylinder_mesh(CAP_R, CAP_H, CAP_SEG)
    cap = b.add_mesh("scroll-cap", cap_verts, [(3, cap_idx)])

    gltf = {
        "asset": {"version": "2.0",
                  "generator": "PSLM v4 scene part (bible-cartridges)"},
        "scene": 0,
        "scenes": [{"name": "psalm-world",
                    "nodes": [0, 1, 2, 3]}],
        "nodes": [
            {"name": "palace",
             "extensions": {"PSLM_part": {
                 "part": "palace",
                 "role": "palace",
                 "recenter": "subtract bounding-box center x/z and box minimum height so the floor sits at height 0",
                 "floor": {
                     "detect": "flattest mesh by height over max(width, depth)",
                     "align": "subtract floor center height from the scene height"},
                 "material": {
                     "baseColorFactor": srgb_to_linear(COLORS["palace_metal"]) + [1.0],
                     "metallicFactor": 1.0,
                     "roughnessFactor": 0.05,
                     "doubleSided": True,
                     "environmentIntensity": 1.25},
                 "material_applies_to": "every mesh except the floor mesh"}}},
            {"name": "scroll", "translation": SCROLL_POS,
             "children": [4, 5, 6, 7, 8, 9, 10, 11, 12]},
            {"name": "camera", "camera": 0,
             "translation": [0.0, 2.0, 11.0],
             "rotation": quat_axis_angle((1, 0, 0), -0.06)},
            {"name": "sun",
             "extensions": {"KHR_lights_punctual": {"light": 0}},
             "translation": [20.0, 30.0, 10.0],
             "rotation": look_at_quat((20.0, 30.0, 10.0), (0.0, 0.0, 0.0))},
            {"name": "scroll-sheet", "mesh": sheet,
             "translation": [0.0, 0.0, SHEET_Z]},
            {"name": "scroll-roll-left", "mesh": roll,
             "translation": [-ROLL_X, 0.0, 0.0]},
            {"name": "scroll-roll-right", "mesh": roll,
             "translation": [ROLL_X, 0.0, 0.0]},
            {"name": "scroll-rod-left", "mesh": rod,
             "translation": [-ROLL_X, 0.0, 0.0]},
            {"name": "scroll-rod-right", "mesh": rod,
             "translation": [ROLL_X, 0.0, 0.0]},
            {"name": "scroll-cap-top-left", "mesh": cap,
             "translation": [-ROLL_X, CAP_Y, 0.0]},
            {"name": "scroll-cap-top-right", "mesh": cap,
             "translation": [ROLL_X, CAP_Y, 0.0]},
            {"name": "scroll-cap-bottom-left", "mesh": cap,
             "translation": [-ROLL_X, -CAP_Y, 0.0]},
            {"name": "scroll-cap-bottom-right", "mesh": cap,
             "translation": [ROLL_X, -CAP_Y, 0.0]},
        ],
        "meshes": b.meshes,
        "materials": [
            {"name": "sheet-edge",
             "pbrMetallicRoughness": {
                 "baseColorFactor": srgb_to_linear(COLORS["sheet_edge"]) + [1.0],
                 "metallicFactor": 0.0, "roughnessFactor": 0.9}},
            {"name": "scroll-text",
             "pbrMetallicRoughness": {
                 "baseColorTexture": {"index": 0},
                 "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
                 "metallicFactor": 0.0, "roughnessFactor": 0.9}},
            {"name": "roll",
             "pbrMetallicRoughness": {
                 "baseColorFactor": srgb_to_linear(COLORS["roll"]) + [1.0],
                 "metallicFactor": 0.0, "roughnessFactor": 0.85}},
            {"name": "wood",
             "pbrMetallicRoughness": {
                 "baseColorFactor": srgb_to_linear(COLORS["wood"]) + [1.0],
                 "metallicFactor": 0.0, "roughnessFactor": 0.8}},
        ],
        "textures": [{"source": 0, "sampler": 0}],
        "images": [{"name": "scroll-text", "uri": "scroll-text"}],
        "samplers": [{"magFilter": 9729, "minFilter": 9729,
                      "wrapS": 33071, "wrapT": 10497}],
        "cameras": [{"name": "camera", "type": "perspective",
                     "perspective": {"yfov": 1.0471975511965976,
                                     "znear": 0.1, "zfar": 500.0}}],
        "extensionsUsed": ["KHR_lights_punctual", "PSLM_part"],
        "extensionsRequired": ["KHR_lights_punctual", "PSLM_part"],
        "extensions": {
            "KHR_lights_punctual": {
                "lights": [{"name": "sun", "type": "directional",
                            "color": srgb_to_linear(COLORS["sun"]),
                            "intensity": 1.6}]}},
        "buffers": [{"byteLength": len(b.buf),
                     "uri": "data:application/octet-stream;base64," +
                            base64.b64encode(bytes(b.buf)).decode("ascii")}],
        "bufferViews": b.buffer_views,
        "accessors": b.accessors,
    }

    scene = {
        "version": 1,
        "gltf": gltf,
        "renderer": {
            "antialias": True,
            "background_fallback": "#0b1020",
            "exposure": 1.0,
            "output_color_space": "sRGB",
            "pixel_ratio_cap": 2,
            "tone_mapping": "ACES filmic",
        },
        "sky": {
            "source_part": "skybox",
            "source": "the panorama image embedded in the skybox glTF part (the first material's emissive texture, else the specular-glossiness diffuse texture)",
            "mapping": "equirectangular",
            "flip_horizontal": True,
            "shift_rows": 80,
            "pole_band_heal": {
                "enabled": True, "fade_rows": 100, "pole_band_top": 0.92,
                "reference_band": [0.65, 0.8], "seam_blur_px": 2},
            "texture": {
                "color_space": "sRGB", "flip_vertical": False,
                "generate_mipmaps": False, "mag_filter": "linear",
                "min_filter": "linear", "wrap_s": "repeat", "wrap_t": "repeat"},
            "background": "use the prepared panorama as the scene background",
            "environment": "use the prepared panorama as the image-based lighting environment (ambient light and reflections for the whole scene)",
        },
        "scroll_text": {
            "texture_name": "scroll-text",
            "background": "#efe3c0",
            "canvas_width": 1400,
            "color_space": "sRGB",
            "font": {"families": ["Noto Serif Hebrew", "Noto Serif",
                                  "Times New Roman", "serif"],
                     "size_px": 46, "weight": "normal"},
            "font_bold": {"families": ["Noto Serif Hebrew", "Noto Serif",
                                       "Times New Roman", "serif"],
                          "size_px": 58, "weight": "bold"},
            "font_separator": {"families": ["Noto Serif Hebrew", "Noto Serif",
                                            "Times New Roman", "serif"],
                               "size_px": 34, "weight": "normal"},
            "layout": {
                "head": {"align": "center", "direction": "ltr", "font": "font_bold"},
                "separator": {"align": "center", "direction": "ltr",
                              "font": "font_separator"},
                "text": {"align": "right", "direction": "rtl", "font": "font"},
                "wrap": "measure text, max width canvas_width - 2*padding"},
            "line_height": 78,
            "min_height": 700,
            "padding": 80,
            "separator_format": "\u2014 N \u2014",
            "text_color": "#2a2118",
            "texture": {"wrap_s": "clamp_to_edge", "wrap_t": "repeat"},
            "word_format": "Hebrew (transliteration, gloss)",
        },
        "animation": {
            "scroll_bob": {
                "node": "scroll", "property": "translation.y",
                "amplitude": 0.12, "frequency": 0.8,
                "formula": "translation.y = glTF translation.y + amplitude * sin(time * frequency)"},
        },
        "controls": {
            "drag_look": {"pitch_clamp": [-1.2, 1.2], "sensitivity": 0.004},
            "drag_scroll": {"sensitivity": 0.002},
            "joystick": {
                "dead_zone": 0.12,
                "note": "a circular on-screen pad at the bottom left; the pointer offset from the pad center, divided by the pad radius and clamped to length 1, is the movement vector; the knob indicator follows that normalized offset"},
            "move": {
                "keys": {"down": ["s", "arrowdown"], "left": ["a", "arrowleft"],
                         "right": ["d", "arrowright"], "up": ["w", "arrowup"]},
                "radius_clamp": 11, "speed": 4},
            "tap_audio": {"max_move_px": 8, "max_time_ms": 500},
            "wheel_scroll": {"sensitivity": 0.0008},
        },
        "audio": {"mime": "audio/webm", "source_part": "audio"},
    }
    return scene


def validate(gltf):
    """Structural check of the glTF document (bounds, counts, references)."""
    bufs = gltf["buffers"]
    assert len(bufs) == 1
    blob = base64.b64decode(bufs[0]["uri"].split(",", 1)[1])
    assert len(blob) == bufs[0]["byteLength"], "buffer length mismatch"
    for i, bv in enumerate(gltf["bufferViews"]):
        assert bv["byteOffset"] + bv["byteLength"] <= len(blob), f"bufferView {i} out of range"
    comp_size = {5126: 4, 5125: 4, 5123: 2}
    type_n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
    for i, a in enumerate(gltf["accessors"]):
        bv = gltf["bufferViews"][a["bufferView"]]
        need = a["count"] * type_n[a["type"]] * comp_size[a["componentType"]]
        assert bv["byteOffset"] + need <= len(blob), f"accessor {i} out of range"
        if a["type"] == "POSITION":
            assert "min" in a and "max" in a, "POSITION accessor needs min/max"
    # index accessors reference existing vertices
    for mi, m in enumerate(gltf["meshes"]):
        for pi, p in enumerate(m["primitives"]):
            npos = gltf["accessors"][p["attributes"]["POSITION"]]["count"]
            ia = gltf["accessors"][p["indices"]]
            bv = gltf["bufferViews"][ia["bufferView"]]
            idx = struct.unpack_from(f"<{ia['count']}I", blob, bv["byteOffset"])
            assert max(idx) < npos, f"mesh {mi} prim {pi} index out of range"
            assert p["material"] < len(gltf["materials"])
    for n in gltf["nodes"]:
        if "mesh" in n:
            assert n["mesh"] < len(gltf["meshes"])
        if "camera" in n:
            assert n["camera"] < len(gltf["cameras"])
        for c in n.get("children", []):
            assert c < len(gltf["nodes"])
    assert gltf["scenes"][gltf["scene"]]["nodes"]
    # camera quaternion is unit length
    q = gltf["nodes"][2]["rotation"]
    assert abs(math.sqrt(sum(v * v for v in q)) - 1.0) < 1e-6, "camera quaternion not unit"
    q = gltf["nodes"][3]["rotation"]
    assert abs(math.sqrt(sum(v * v for v in q)) - 1.0) < 1e-6, "sun quaternion not unit"
    # sun -Z points at the origin: rotate (0,0,-1) by the sun quaternion
    x, y, z, w = q
    # rotate v=(0,0,-1): v' = q * v * q^-1
    def qrot(v):
        vx, vy, vz = v
        tx = 2 * (y * vz - z * vy)
        ty = 2 * (z * vx - x * vz)
        tz = 2 * (x * vy - y * vx)
        return (vx + w * tx + y * tz - z * ty,
                vy + w * ty + z * tx - x * tz,
                vz + w * tz + x * ty - y * tx)
    d = qrot((0, 0, -1))
    eye = gltf["nodes"][3]["translation"]
    want = [-e / math.sqrt(sum(v * v for v in eye)) for e in eye]
    assert all(abs(a - b) < 1e-6 for a, b in zip(d, want)), "sun -Z does not point at origin"
    return blob


def main():
    scene = build_scene()
    blob = validate(scene["gltf"])
    out = Path(__file__).resolve().parent / "scene.json"
    text = json.dumps(scene, indent=1, ensure_ascii=False)
    out.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(text)} bytes, buffer {len(blob)} bytes)")
    print(f"  nodes: {len(scene['gltf']['nodes'])}, meshes: {len(scene['gltf']['meshes'])}, "
          f"materials: {len(scene['gltf']['materials'])}, accessors: {len(scene['gltf']['accessors'])}")
    print(f"  camera quat: {scene['gltf']['nodes'][2]['rotation']}")
    print(f"  sun quat: {scene['gltf']['nodes'][3]['rotation']}")
    print(f"  sun colour (linear): {scene['gltf']['extensions']['KHR_lights_punctual']['lights'][0]['color']}")
    print(f"  palace metal baseColorFactor: {scene['gltf']['nodes'][0]['extensions']['PSLM_part']['material']['baseColorFactor']}")


if __name__ == "__main__":
    main()

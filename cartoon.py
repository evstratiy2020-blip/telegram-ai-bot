import math
import os
import subprocess
import tempfile
import wave
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw

W = H = 360

CHARS = [
    dict(name="Кепка", skin=(247, 214, 180), hair=(55, 40, 30), style="short", acc="cap", beard="none", cloth=(40, 90, 160)),
    dict(name="Профессор", skin=(240, 200, 165), hair=(205, 205, 208), style="short", acc="round_glasses", beard="full", cloth=(30, 140, 90)),
    dict(name="Девушка", skin=(250, 220, 190), hair=(205, 150, 60), style="long", acc="bow", beard="none", cloth=(205, 80, 140)),
    dict(name="Робот", skin=(200, 210, 220), hair=(150, 160, 175), style="bald", acc="antenna", beard="none", cloth=(90, 95, 110)),
    dict(name="Бородач", skin=(235, 195, 160), hair=(80, 55, 45), style="short", acc="none", beard="full", cloth=(120, 80, 170)),
    dict(name="Мужчина", style="man3d"),
    dict(name="Женщина", style="woman3d"),
    dict(name="Робот 3D", style="robot3d"),
    dict(name="Боня", style="bonya"),
]


def _radial(img, box, c_in, c_out, lx=-0.22, ly=-0.32, shape="ellipse", radius=28):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = (xx / w - (0.5 + lx)) * 1.45
    ny = (yy / h - (0.5 + ly)) * 1.45
    rr = np.clip(np.sqrt(nx * nx + ny * ny), 0, 1)
    a = np.array(c_in, dtype=np.float32)
    b = np.array(c_out, dtype=np.float32)
    arr = (a[None, None, :] * (1 - rr[..., None]) + b[None, None, :] * rr[..., None]).astype(np.uint8)
    patch = Image.fromarray(arr, "RGB")
    m = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(m)
    if shape == "ellipse":
        md.ellipse([0, 0, w - 1, h - 1], fill=255)
    elif shape == "rect":
        md.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    else:
        md.chord([0, 0, w - 1, h - 1], 180, 360, fill=255)
    img.paste(patch, (x0, y0), m)


def _eyes3d(d, cx, cy, ex, iris, blink):
    if blink <= 0.2:
        for sx in (-ex, ex):
            d.line([cx + sx - 22, cy, cx + sx + 22, cy], fill=(60, 45, 40), width=5)
        return
    for sx in (-ex, ex):
        d.ellipse([cx + sx - 26, cy - 20, cx + sx + 26, cy + 20], fill=(250, 250, 252), outline=(120, 90, 70), width=2)
        d.ellipse([cx + sx - 12, cy - 12, cx + sx + 12, cy + 12], fill=iris)
        d.ellipse([cx + sx - 6, cy - 6, cx + sx + 6, cy + 6], fill=(20, 16, 16))
        d.ellipse([cx + sx - 8, cy - 13, cx + sx - 2, cy - 7], fill=(255, 255, 255))


def _mouth3d(d, cx, cy, a, w, lip):
    mh = int(6 + 40 * a)
    d.ellipse([cx - w, cy, cx + w, cy + mh], fill=(70, 18, 24), outline=lip, width=3)
    if mh > 18:
        d.ellipse([cx - w + 16, cy + mh - 24, cx + w - 16, cy + mh - 4], fill=(210, 90, 105))


def draw_man(a, blink=1.0):
    img = Image.new("RGB", (W, H), (246, 249, 253))
    d = ImageDraw.Draw(img)
    cx, cy, r = W // 2, H // 2 + 12, 116
    _radial(img, [cx - 122, cy + r - 46, cx + 122, cy + r + 150], (78, 140, 216), (24, 64, 132), -0.2, -0.5, "rect", 34)
    for sx in (-1, 1):
        _radial(img, [cx + sx * 90 - 18, cy + r - 30, cx + sx * 90 + 18, cy + r + 60], (86, 148, 222), (30, 72, 140), -0.2, -0.4)
    for sx in (-1, 1):
        _radial(img, [cx + sx * (r - 6) - 14, cy - 6, cx + sx * (r - 6) + 14, cy + 46], (250, 220, 188), (198, 152, 116), -0.2, -0.3)
    _radial(img, [cx - r, cy - r, cx + r, cy + r], (253, 224, 192), (198, 150, 112), -0.24, -0.34)
    d.chord([cx - r - 4, cy - r - 6, cx + r + 4, cy + 6], 180, 360, fill=(40, 32, 28))
    d.arc([cx - r, cy - r, cx + r, cy - 20], 200, 320, fill=(82, 66, 54), width=5)
    d.polygon([(cx - 6, cy - 24), (cx - 20, cy + 30), (cx + 16, cy + 30)], fill=(224, 176, 138))
    d.polygon([(cx - 6, cy - 24), (cx + 16, cy + 30), (cx + 2, cy + 30)], fill=(196, 146, 108))
    for sx in (-1, 1):
        d.line([cx + sx * 50 - 30, cy - 66, cx + sx * 50 + 30, cy - 74], fill=(46, 36, 30), width=7)
    _eyes3d(d, cx, cy - 36, 50, (76, 122, 168), blink)
    _mouth3d(d, cx, cy + 52, a, 62, (168, 96, 84))
    return img


def draw_woman(a, blink=1.0):
    img = Image.new("RGB", (W, H), (246, 249, 253))
    d = ImageDraw.Draw(img)
    cx, cy, r = W // 2, H // 2 + 12, 116
    d.rounded_rectangle([cx - r - 30, cy - r + 10, cx - r + 22, cy + r + 120], 18, fill=(120, 70, 40))
    d.rounded_rectangle([cx + r - 22, cy - r + 10, cx + r + 30, cy + r + 120], 18, fill=(120, 70, 40))
    _radial(img, [cx - 122, cy + r - 46, cx + 122, cy + r + 150], (236, 110, 170), (150, 40, 110), -0.2, -0.5, "rect", 34)
    _radial(img, [cx - r, cy - r, cx + r, cy + r], (255, 229, 206), (214, 166, 136), -0.24, -0.34)
    _radial(img, [cx - r - 8, cy - r - 12, cx + r + 8, cy + 30], (140, 85, 45), (70, 40, 22), -0.2, -0.4, "chord")
    d.chord([cx - r - 4, cy - r - 4, cx + r + 4, cy + 8], 180, 360, fill=(96, 58, 32))
    for sx in (-1, 1):
        d.ellipse([cx + sx * 48 - 30, cy + 22, cx + sx * 48 + 30, cy + 44], fill=(236, 140, 150))
    for sx in (-1, 1):
        d.line([cx + sx * 50 - 26, cy - 62, cx + sx * 50 + 26, cy - 70], fill=(80, 52, 34), width=6)
    _eyes3d(d, cx, cy - 36, 50, (60, 110, 90), blink)
    d.polygon([(cx, cy - 16), (cx - 7, cy + 18), (cx + 7, cy + 18)], fill=(238, 196, 168))
    _mouth3d(d, cx, cy + 54, a, 54, (196, 40, 70))
    return img


def draw_robot3d(a, blink=1.0):
    img = Image.new("RGB", (W, H), (246, 249, 253))
    d = ImageDraw.Draw(img)
    cx, cy, r = W // 2, H // 2 + 12, 112
    _radial(img, [cx - 120, cy + r - 40, cx + 120, cy + r + 150], (120, 150, 190), (40, 60, 96), -0.2, -0.5, "rect", 30)
    d.line([cx, cy - r - 34, cx, cy - r - 6], fill=(150, 160, 180), width=7)
    d.ellipse([cx - 12, cy - r - 54, cx + 12, cy - r - 30], fill=(80, 220, 255))
    d.ellipse([cx - 20, cy - r - 62, cx + 20, cy - r - 22], outline=(80, 220, 255), width=2)
    for sx in (-1, 1):
        _radial(img, [cx + sx * (r - 4) - 12, cy - 22, cx + sx * (r - 4) + 12, cy + 34], (200, 214, 232), (120, 138, 164), -0.2, -0.3)
    _radial(img, [cx - r, cy - r, cx + r, cy + r], (238, 244, 252), (150, 166, 190), -0.26, -0.34)
    for sx in (-1, 1):
        d.ellipse([cx + sx * 46 - 26, cy - 58, cx + sx * 46 + 26, cy - 6], fill=(18, 28, 46))
        if blink > 0.2:
            d.ellipse([cx + sx * 46 - 16, cy - 48, cx + sx * 46 + 16, cy - 16], fill=(80, 220, 255))
            d.ellipse([cx + sx * 46 - 10, cy - 44, cx + sx * 46 + 10, cy - 20], fill=(200, 250, 255))
        else:
            d.line([cx + sx * 46 - 22, cy - 32, cx + sx * 46 + 22, cy - 32], fill=(80, 220, 255), width=5)
    d.rounded_rectangle([cx - 44, cy + 44, cx + 44, cy + 76], 12, fill=(18, 28, 46))
    mh = int(6 + 22 * a)
    d.rounded_rectangle([cx - 34, cy + 48, cx + 34, cy + 48 + mh], radius=min(mh / 2, 12), fill=(80, 220, 255))
    return img


def _eye(d, x, y, r, look=3, robot=False):
    d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255), outline=(70, 50, 40), width=3)
    if robot:
        d.rectangle([x - r, y - r, x + r, y + r], outline=(70, 50, 40), width=3)
        d.rectangle([x - r * 0.5, y - r * 0.6, x + r * 0.5, y + r * 0.6], fill=(60, 120, 200))
    else:
        d.ellipse([x - r * 0.45 + look, y - r * 0.45, x + r * 0.45 + look, y + r * 0.45], fill=(50, 70, 110))
        d.ellipse([x - r * 0.2 + look, y - r * 0.2, x + r * 0.2 + look, y + r * 0.2], fill=(15, 15, 15))


def _mouth(d, cx, cy, a, w=70, color=(150, 40, 50)):
    mh = int(6 + 40 * a)
    d.ellipse([cx - w, cy, cx + w, cy + mh], fill=color, outline=(90, 20, 25), width=3)
    if mh > 20:
        d.ellipse([cx - w + 14, cy + mh - 22, cx + w - 14, cy + mh - 4], fill=(235, 140, 150))


def draw_bonya(a, blink=1.0):
    img = Image.new("RGB", (W, H), (246, 249, 253))
    d = ImageDraw.Draw(img)
    cx, cy = W // 2, H // 2 + 10
    d.rounded_rectangle([cx - 162, cy - 34, cx - 138, cy + 34], 9, fill=(59, 130, 246))
    d.rounded_rectangle([cx + 138, cy - 34, cx + 162, cy + 34], 9, fill=(59, 130, 246))
    d.line([cx, cy - 152, cx, cy - 122], fill=(139, 92, 246), width=7)
    d.ellipse([cx - 13, cy - 176, cx + 13, cy - 150], fill=(76, 201, 240))
    d.rounded_rectangle([cx - 128, cy - 122, cx + 128, cy + 122], 62, fill=(43, 60, 102), outline=(80, 100, 150), width=3)
    for ex in (-72, 72):
        d.ellipse([cx + ex - 11, cy + 40, cx + ex + 11, cy + 62], fill=(120, 90, 200))
    for ex in (-46, 46):
        if blink > 0.2:
            er = 20
            d.ellipse([cx + ex - er, cy - 32 - er, cx + ex + er, cy - 32 + er], fill=(11, 18, 32))
            d.ellipse([cx + ex - 9, cy - 32 - 9, cx + ex + 9, cy - 32 + 9], fill=(76, 201, 240))
            d.ellipse([cx + ex - 7, cy - 44, cx + ex - 1, cy - 36], fill=(255, 255, 255))
        else:
            d.line([cx + ex - 20, cy - 32, cx + ex + 20, cy - 32], fill=(76, 201, 240), width=6)
    mh = 8 + 34 * a
    d.rounded_rectangle([cx - 26, cy + 46, cx + 26, cy + 46 + mh], radius=min(mh / 2, 15), fill=(11, 18, 32))
    return img


def draw_char(idx, a, blink=1.0):
    c = CHARS[idx % len(CHARS)]
    st = c.get("style")
    if st == "bonya":
        return draw_bonya(a, blink)
    if st == "man3d":
        return draw_man(a, blink)
    if st == "woman3d":
        return draw_woman(a, blink)
    if st == "robot3d":
        return draw_robot3d(a, blink)
    img = Image.new("RGB", (W, H), (246, 249, 253))
    d = ImageDraw.Draw(img)
    cx, cy, r = W // 2, H // 2 + 12, 116
    skin, hair, cloth = c["skin"], c["hair"], c["cloth"]
    d.rounded_rectangle([cx - 110, cy + r - 30, cx + 110, cy + r + 130], 28, fill=cloth)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=skin, outline=(120, 85, 60), width=4)
    st = c["style"]
    if st == "short":
        d.chord([cx - r - 6, cy - r - 8, cx + r + 6, cy + 20], 180, 360, fill=hair)
    elif st == "long":
        d.chord([cx - r - 6, cy - r - 8, cx + r + 6, cy + 20], 180, 360, fill=hair)
        d.rounded_rectangle([cx - r - 14, cy - 40, cx - r + 26, cy + r + 40], 16, fill=hair)
        d.rounded_rectangle([cx + r - 26, cy - 40, cx + r + 14, cy + r + 40], 16, fill=hair)
    elif st == "curly":
        for ang in range(180, 361, 30):
            x = cx + (r + 6) * math.cos(math.radians(ang))
            y = cy + (r + 6) * math.sin(math.radians(ang))
            d.ellipse([x - 32, y - 32, x + 32, y + 32], fill=hair)
    elif st == "mohawk":
        d.polygon([(cx - 18, cy - r + 10), (cx, cy - r - 70), (cx + 18, cy - r + 10)], fill=hair)
        d.chord([cx - r, cy - r + 10, cx + r, cy + 30], 180, 360, fill=hair)
    er = 26 - int(14 * (1 - blink))
    for ex in (-52, 52):
        if blink > 0.2:
            _eye(d, cx + ex, cy - 34, er, robot=(c["acc"] == "antenna"))
        else:
            d.line([cx + ex - 24, cy - 34, cx + ex + 24, cy - 34], fill=(70, 50, 40), width=5)
    for ex in (-52, 52):
        d.line([cx + ex - 26, cy - 72, cx + ex + 26, cy - 80], fill=hair, width=6)
    d.polygon([(cx, cy - 15), (cx - 9, cy + 16), (cx + 9, cy + 16)], fill=(210, 165, 125))
    b = c["beard"]
    if b == "full":
        d.chord([cx - 72, cy + 24, cx + 72, cy + 150], 0, 180, fill=hair)
    _mouth(d, cx, cy + 46, a)
    if b == "mustache":
        d.chord([cx - 40, cy + 14, cx + 40, cy + 52], 0, 180, fill=hair)
    acc = c["acc"]
    if acc == "cap":
        d.pieslice([cx - r - 8, cy - r - 26, cx + r + 8, cy + r - 50], 180, 360, fill=(205, 60, 60))
        d.rounded_rectangle([cx - r - 34, cy - r - 4, cx + r + 34, cy - r + 14], 10, fill=(205, 60, 60))
    elif acc in ("glasses", "round_glasses"):
        rr = 40 if acc == "glasses" else 30
        for ex in (-52, 52):
            d.ellipse([cx + ex - rr, cy - 34 - rr, cx + ex + rr, cy - 34 + rr], outline=(40, 40, 45), width=6)
        d.line([cx - 14, cy - 34, cx + 14, cy - 34], fill=(40, 40, 45), width=6)
    elif acc == "bow":
        for bx in (-92, 92):
            d.ellipse([cx + bx - 30, cy - r - 24, cx + bx + 30, cy - r + 12], fill=(230, 60, 120))
        d.ellipse([cx - 12, cy - r - 18, cx + 12, cy - r + 6], fill=(250, 200, 60))
    elif acc == "antenna":
        d.rectangle([cx - 4, cy - r - 26, cx + 4, cy - r], fill=(120, 125, 140))
        d.ellipse([cx - 12, cy - r - 48, cx + 12, cy - r - 24], fill=(250, 90, 90))
    elif acc == "crown":
        d.polygon([(cx - 60, cy - r - 6), (cx - 60, cy - r - 56), (cx - 30, cy - r - 20),
                   (cx, cy - r - 66), (cx + 30, cy - r - 20), (cx + 60, cy - r - 56),
                   (cx + 60, cy - r - 6)], fill=(245, 200, 40))
    return img


def grid_png() -> bytes:
    cols, rows, cell = 5, 2, 190
    sheet = Image.new("RGB", (cols * cell, rows * cell), (246, 249, 253))
    for i in range(len(CHARS)):
        sheet.paste(draw_char(i, 0.0).resize((cell, cell)), ((i % cols) * cell, (i // cols) * cell))
    buf = BytesIO()
    sheet.save(buf, "PNG")
    return buf.getvalue()


def _ff(args):
    subprocess.run(["ffmpeg", "-y", *args], check=True, capture_output=True)


def render_video(char_idx: int, audio_path: str, out_mp4: str, size: int = 260, fps: int = 25) -> str:
    work = tempfile.mkdtemp(prefix="cart_")
    wav = os.path.join(work, "a.wav")
    _ff(["-i", audio_path, "-ac", "1", "-ar", "22050", wav])
    with wave.open(wav) as w:
        sr = w.getframerate()
        raw = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    dur = len(raw) / sr
    n = int(dur * fps) + 1
    win = max(1, int(sr / fps))
    env = []
    for i in range(n):
        seg = raw[i * win:(i + 1) * win]
        env.append(float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0)
    mx = max(env) or 1.0
    env = [min(1.0, e / mx * 1.7) for e in env]
    fd = os.path.join(work, "f")
    os.makedirs(fd, exist_ok=True)
    for k, a in enumerate(env):
        blink = 1.0 if (k % 47) > 3 else 0.0
        draw_char(char_idx, a, blink).resize((size, size)).save(os.path.join(fd, f"f{k:04d}.png"))
    _ff(["-framerate", str(fps), "-i", os.path.join(fd, "f%04d.png"), "-i", audio_path,
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
         "-movflags", "+faststart", out_mp4])
    return out_mp4

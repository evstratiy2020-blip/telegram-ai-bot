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
    dict(name="Модник", skin=(120, 85, 60), hair=(20, 20, 25), style="mohawk", acc="glasses", beard="mustache", cloth=(25, 25, 30)),
    dict(name="Кудрявый", skin=(250, 224, 196), hair=(185, 95, 45), style="curly", acc="none", beard="none", cloth=(240, 170, 40)),
    dict(name="Король", skin=(245, 210, 175), hair=(210, 180, 60), style="short", acc="crown", beard="mustache", cloth=(150, 30, 50)),
    dict(name="Боня", style="bonya"),
]


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
    if c.get("style") == "bonya":
        return draw_bonya(a, blink)
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

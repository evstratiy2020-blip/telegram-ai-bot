import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import tempfile
import wave

# deploy marker: music styles v2
from pathlib import Path
from urllib.parse import parse_qsl, quote

import edge_tts
import httpx

try:
    import parselmouth
    from parselmouth.praat import call as praat_call
except Exception:  # noqa: BLE001
    parselmouth = None
    praat_call = None

try:
    import numpy as np
except Exception:  # noqa: BLE001
    np = None
from aiogram import BaseMiddleware, Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    MenuButtonDefault,
    MenuButtonWebApp,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "8768178048"))
SITE_PASSWORD_HASH = os.getenv(
    "SITE_PASSWORD_HASH",
    "pbkdf2_sha256$ZAFv7Zpy2VxigCK5a9Qzpw==$G4QpmNzINw7xdoI7ESRU/ZJRHjgbMsmJVAdoOSI0Ms8=",
)
SESSION_TOKEN = hmac.new(BOT_TOKEN.encode(), b"site-session-v1", hashlib.sha256).hexdigest()
APP_KEY = hmac.new(BOT_TOKEN.encode(), b"app-key-v1", hashlib.sha256).hexdigest()[:24]
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/")
LLM_URL = f"{LLM_BASE_URL}/chat/completions"

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
PORT = int(os.getenv("PORT", "7860"))
HOST = os.getenv("HOST", "0.0.0.0")

MINIAPP_URL = os.getenv("MINIAPP_URL", "")
STATIC_DIR = Path(__file__).parent / "static"

RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")
if RENDER_URL:
    if not WEBHOOK_URL:
        WEBHOOK_URL = RENDER_URL + WEBHOOK_PATH
    if not MINIAPP_URL:
        MINIAPP_URL = RENDER_URL + "/app?k=" + APP_KEY

SYSTEM_PROMPT = (
    "Ты — полезный ИИ-ассистент в Telegram. "
    "Отвечай на языке собеседника (по умолчанию на русском), "
    "очень кратко (1-3 предложения), понятно и по делу. "
    "Отвечай обычным текстом без markdown: не используй звёздочки (*, **), "
    "решётки (#), нижние подчёркивания (_) и обратные кавычки (`)."
)

FFMPEG = os.getenv("FFMPEG_PATH", "ffmpeg")

ABOUT_TEXT = (
    "Я Боня-Navigator, железный робот-помощник. 🤖\n"
    "Умею: отвечать на вопросы, помнить наш диалог и говорить голосом.\n\n"
    "Выбери мне голос кнопкой 🎙 и просто поговори со мной."
)

FLANGER = "flanger=delay=8:depth=3:regen=0.2:width=71:speed=0.5"
RING = "aeval='val(0)*sin(2*PI*55*t)'"

VOICE_PRESETS = {
    "bonya": {
        "name": "Боня",
        "voice": "ru-RU-DmitryNeural",
        "rate": "-15%",
        "pitch": "+80Hz",
        "fx": FLANGER,
    },
    "ring": {
        "name": "Робот-металл",
        "voice": "ru-RU-DmitryNeural",
        "rate": "-15%",
        "pitch": "+60Hz",
        "fx": RING,
    },
    "mono": {
        "name": "Робот-монотонный",
        "voice": "ru-RU-DmitryNeural",
        "rate": "-15%",
        "pitch": "+60Hz",
        "mono": 175,
    },
}
DEFAULT_PRESET = "bonya"

IMAGE_URL = "https://image.pollinations.ai/prompt/{prompt}?width=1024&height=1024&enhance=true&nologo=true"

HISTORY_LIMIT = 20

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

history: dict[int, list[dict]] = {}
voice_enabled: set[int] = set()
voice_settings: dict[int, str] = {}
image_mode: set[int] = set()
sing_mode: set[int] = set()
music_settings: dict[int, str] = {}
memory_facts: list[str] = []


class OwnerOnlyMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if OWNER_ID and (user is None or user.id != OWNER_ID):
            if isinstance(event, Message):
                try:
                    await event.answer("Извини, это приватный бот.")
                except Exception:
                    pass
            return None
        return await handler(event, data)


dp.message.outer_middleware(OwnerOnlyMiddleware())
dp.callback_query.outer_middleware(OwnerOnlyMiddleware())


def voice_keyboard() -> InlineKeyboardMarkup:
    rows = []
    items = list(VOICE_PRESETS.items())
    for i in range(0, len(items), 2):
        row = [
            InlineKeyboardButton(text=data["name"], callback_data=f"voice:{key}")
            for key, data in items[i:i + 2]
        ]
        rows.append(row)
    rows.append([InlineKeyboardButton(text="🔇 Выключить голос", callback_data="voice:off")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


MUSIC_NAMES = {
    "none": "Без музыки",
    "bassbeat": "Бас + бит",
    "marimba": "Маримба",
    "rock": "Рок",
    "jazz": "Джаз",
    "country": "Кантри",
    "hiphop": "Хип-хоп",
    "bit": "8-бит",
    "ethnic": "Этно",
    "sad": "Грустный",
    "disco": "Диско",
}


def music_keyboard() -> InlineKeyboardMarkup:
    rows = []
    items = list(MUSIC_NAMES.items())
    for i in range(0, len(items), 2):
        rows.append([
            InlineKeyboardButton(text=data, callback_data=f"music:{key}")
            for key, data in items[i:i + 2]
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def voice_music_keyboard(uid: int) -> InlineKeyboardMarkup:
    cur_voice = voice_settings.get(uid, DEFAULT_PRESET)
    cur_music = music_settings.get(uid, "none")
    rows = [[
        InlineKeyboardButton(
            text=("✅ " if key == cur_voice else "") + data["name"],
            callback_data=f"voice:{key}",
        )
        for key, data in VOICE_PRESETS.items()
    ]]
    items = list(MUSIC_NAMES.items())
    for i in range(0, len(items), 2):
        rows.append([
            InlineKeyboardButton(
                text=("✅ " if key == cur_music else "") + data,
                callback_data=f"music:{key}",
            )
            for key, data in items[i:i + 2]
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_keyboard() -> ReplyKeyboardMarkup:
    row = [
        KeyboardButton(text="🎙 Голос"),
        KeyboardButton(text="🔇 Молчать"),
        KeyboardButton(text="🎼 Песни"),
        KeyboardButton(text="🎶 Музыка"),
    ]
    if MINIAPP_URL:
        row.append(KeyboardButton(text="🚀 Боня", web_app=WebAppInfo(url=MINIAPP_URL)))
    keyboard = [row]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_history(uid: int) -> list[dict]:
    return history.setdefault(uid, [])


def strip_markdown(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    return text


def get_webapp_user_id(init_data: str) -> int | None:
    if not init_data:
        return None
    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True))
    except Exception:
        return None
    received = pairs.pop("hash", None)
    if not received:
        return None
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received):
        return None
    try:
        user = json.loads(pairs.get("user", "{}"))
    except Exception:
        return None
    return user.get("id")


def check_password(password: str) -> bool:
    try:
        _algo, salt_b64, hash_b64 = SITE_PASSWORD_HASH.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200000)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


def is_authorized(request) -> bool:
    uid = get_webapp_user_id(request.headers.get("X-Init-Data", ""))
    if OWNER_ID and uid == OWNER_ID:
        return True
    key = request.query.get("k", "")
    if key and hmac.compare_digest(key, APP_KEY):
        return True
    if SITE_PASSWORD_HASH and request.cookies.get("nav_auth") == SESSION_TOKEN:
        return True
    return False


async def ask_llm(messages: list[dict]) -> str:
    system = SYSTEM_PROMPT
    if memory_facts:
        system += "\n\nЧто ты помнишь о пользователе (учитывай это):\n" + "\n".join(f"- {f}" for f in memory_facts)
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "system", "content": system}] + messages,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(LLM_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


async def update_memory(messages: list[dict], reply: str) -> None:
    global memory_facts
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in messages[-6:]) + f"\nassistant: {reply}"
    prompt = (
        "Ниже список фактов о пользователе и последний диалог. Обнови список: "
        "добавь новые важные факты о пользователе (имя, интересы, привычки, важное), убери устаревшее. "
        "Верни только список фактов, каждый с новой строки, без нумерации.\n\n"
        "Текущие факты:\n" + ("\n".join(memory_facts) if memory_facts else "(пусто)") + "\n\nДиалог:\n" + convo
    )
    payload = {"model": LLM_MODEL, "messages": [{"role": "user", "content": prompt}], "stream": False}
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(LLM_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        text = data["choices"][0]["message"]["content"].strip()
        facts = [ln.strip("-• \t") for ln in text.splitlines() if ln.strip()]
        memory_facts = facts[:30]
    except Exception:
        pass


async def generate_voice(text: str, out_path: str, preset_key: str = DEFAULT_PRESET, fmt: str = "ogg") -> None:
    preset = VOICE_PRESETS.get(preset_key, VOICE_PRESETS[DEFAULT_PRESET])
    src = out_path + ".src.mp3"
    communicate = edge_tts.Communicate(text, preset["voice"], rate=preset["rate"], pitch=preset["pitch"])
    await communicate.save(src)
    codec = ["-c:a", "libopus", "-b:a", "64k"] if fmt == "ogg" else ["-c:a", "libmp3lame", "-b:a", "48k", "-ar", "16000"]
    if "mono" in preset and parselmouth is not None:
        wav = out_path + ".src.wav"
        mono_wav = out_path + ".mono.wav"
        await _ffmpeg(["-i", src, "-ac", "1", "-ar", "44100", wav])
        snd = parselmouth.Sound(wav)
        dur = snd.get_total_duration()
        manip = praat_call(snd, "To Manipulation", 0.01, 60, 700)
        tier = praat_call("Create PitchTier", "m", 0.0, dur)
        praat_call(tier, "Add point", 0.0, float(preset["mono"]))
        praat_call(tier, "Add point", dur, float(preset["mono"]))
        praat_call([manip, tier], "Replace pitch tier")
        res = praat_call(manip, "Get resynthesis (overlap-add)")
        res.save(mono_wav, "WAV")
        await _ffmpeg(["-i", mono_wav, *codec, out_path])
        for p in (src, wav, mono_wav):
            if os.path.exists(p):
                os.remove(p)
        return
    filt = preset.get("fx", FLANGER)
    await _ffmpeg(["-i", src, "-af", filt, *codec, out_path])
    if os.path.exists(src):
        os.remove(src)


async def _ffmpeg(args: list[str]) -> None:
    proc = await asyncio.create_subprocess_exec(
        FFMPEG, "-y", *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    rc = await proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed (code {rc})")


SING_SCALE = [262, 294, 330, 294, 392, 330, 294, 262, 330, 294, 262, 220]

SR = 44100
_C = [261.63, 329.63, 392.00]
_Am = [220.00, 261.63, 329.63]
_F = [174.61, 220.00, 261.63]
_G = [196.00, 246.94, 293.66]
MAJOR = [_C, _Am, _F, _G]
SAD = [_Am, _F, _C, _G]
MUSIC_STYLES = {
    "sad": (80, SAD, "sad"),
    "disco": (118, MAJOR, "disco"),
    "bassbeat": (120, MAJOR, "bassbeat"),
    "marimba": (112, MAJOR, "marimba"),
    "rock": (140, MAJOR, "rock"),
    "jazz": (120, MAJOR, "jazz"),
    "country": (116, MAJOR, "country"),
    "hiphop": (90, MAJOR, "hiphop"),
    "bit": (130, MAJOR, "bit"),
    "ethnic": (108, MAJOR, "ethnic"),
}


def _tone(freq, dur, kind):
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    if kind == "pluck":
        sig = sum(a * np.sin(2 * np.pi * freq * h * t) for h, a in [(1, 0.6), (2, 0.3), (3, 0.15)])
        env = np.exp(-t * 6) * np.minimum(1, t * 200)
    elif kind == "bass":
        sig = np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * 2 * freq * t)
        env = np.exp(-t * 3) * np.minimum(1, t * 100)
    elif kind == "marimba":
        sig = sum(a * np.sin(2 * np.pi * freq * h * t) for h, a in [(1, 0.6), (4, 0.2), (10, 0.05)])
        env = np.exp(-t * 8) * np.minimum(1, t * 400)
    elif kind == "dist":
        sig = np.clip((np.sin(2 * np.pi * freq * t) + 0.5 * np.sin(2 * np.pi * 2 * freq * t)) * 1.8, -0.8, 0.8)
        env = np.exp(-t * 3) * np.minimum(1, t * 100)
    elif kind == "square":
        sig = np.sign(np.sin(2 * np.pi * freq * t))
        env = np.exp(-t * 4) * np.minimum(1, t * 300)
    elif kind == "banjo":
        sig = sum(a * np.sin(2 * np.pi * freq * h * t) for h, a in [(1, 0.6), (2, 0.3), (3, 0.2), (5, 0.1)])
        env = np.exp(-t * 9) * np.minimum(1, t * 400)
    else:
        sig = sum(a * np.sin(2 * np.pi * freq * h * t) for h, a in [(1, 0.5), (2, 0.2), (3, 0.08)])
        env = np.minimum(1, t * 8) * np.minimum(1, (dur - t) * 8)
    return sig * env


def _kick(dur=0.25):
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    f = 110 * np.exp(-t * 22) + 45
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)


def _snare(dur=0.18):
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    return (0.8 * np.random.randn(len(t)) + 0.2 * np.sin(2 * np.pi * 190 * t)) * np.exp(-t * 22)


def _tom(dur=0.3, f0=140):
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    f = f0 * np.exp(-t * 12) + 60
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 8)


def _hihat(dur=0.05):
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    return np.random.randn(len(t)) * np.exp(-t * 70)


def _add(track, pos, sig, gain):
    if pos >= len(track):
        return
    e = min(pos + len(sig), len(track))
    track[pos:e] += sig[: e - pos] * gain


def make_music(duration, bpm, chords, style):
    beat = 60.0 / bpm
    n = int(SR * duration) + SR
    track = np.zeros(n)
    bar = beat * 4
    for i in range(int(np.ceil(duration / bar))):
        chord = chords[i % len(chords)]
        base = int(i * bar * SR)
        if style in ("sad", "disco"):
            for f in chord:
                _add(track, base, _tone(f, bar * 0.95, "pad"), 0.45)
        if style == "disco":
            for j in range(4):
                pos = base + int(j * beat * SR)
                _add(track, pos, _kick(), 0.9)
                if j in (1, 3):
                    _add(track, pos, _snare(), 0.5)
                for off in (0.0, beat / 2):
                    _add(track, base + int((j * beat + off) * SR), _hihat(), 0.25)
        elif style == "sad":
            for j in (0, 2):
                _add(track, base + int(j * beat * SR), _kick(), 0.6)
        elif style == "bassbeat":
            for j in range(4):
                pos = base + int(j * beat * SR)
                _add(track, pos, _tone(chord[0] / 2, beat * 0.8, "bass"), 0.6)
                _add(track, pos, _kick() if j in (0, 2) else _snare(), 0.7)
        elif style == "marimba":
            for j in range(8):
                _add(track, base + int(j * beat / 2 * SR), _tone(chord[j % len(chord)], beat * 0.7, "marimba"), 0.35)
        elif style == "rock":
            for j in range(4):
                pos = base + int(j * beat * SR)
                for f in (chord[0], chord[0] * 1.5):
                    _add(track, pos, _tone(f, beat * 0.5, "dist"), 0.3)
                _add(track, pos, _kick() if j % 2 == 0 else _snare(), 0.6)
        elif style == "jazz":
            for j in range(4):
                pos = base + int(j * beat * SR)
                _add(track, pos, _tone(chord[j % len(chord)], beat * 0.7, "pluck"), 0.3)
                if j in (1, 3):
                    _add(track, pos, _snare(), 0.25)
        elif style == "country":
            for j in range(8):
                _add(track, base + int(j * beat / 2 * SR), _tone(chord[j % len(chord)], beat * 0.5, "banjo"), 0.3)
            _add(track, base, _kick(), 0.4)
        elif style == "hiphop":
            _add(track, base, _kick(), 0.9)
            _add(track, base + int(beat * 2 * SR), _kick(), 0.9)
            _add(track, base + int(beat * SR), _snare(), 0.6)
            _add(track, base + int(beat * 3 * SR), _snare(), 0.6)
            for j in range(2):
                _add(track, base + int(j * beat * 2 * SR), _tone(chord[0] / 2, beat * 1.5, "bass"), 0.6)
        elif style == "bit":
            for j in range(16):
                _add(track, base + int(j * beat / 4 * SR), _tone(chord[j % len(chord)], beat * 0.4, "square"), 0.18)
            _add(track, base, _kick(), 0.5)
            _add(track, base + int(beat * 2 * SR), _snare(), 0.4)
        elif style == "ethnic":
            for j in range(4):
                pos = base + int(j * beat * SR)
                _add(track, pos, _kick() if j % 2 == 0 else _tom(0.3, 180), 0.7)
            for j in range(8):
                _add(track, base + int(j * beat / 2 * SR), _tom(0.15, 260), 0.25)
            _add(track, base, _tone(chord[0] / 2, beat * 2, "bass"), 0.5)
    m = float(np.max(np.abs(track))) or 1.0
    return track / m * 0.7


def write_wav(path, data):
    pcm = (np.clip(data, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def _sounding_intervals(snd) -> list:
    tg = praat_call(snd, "To TextGrid (silences)", 100, 0.0, -25.0, 0.08, 0.04, "silent", "sounding")
    n = praat_call(tg, "Get number of intervals", 1)
    spans = []
    for i in range(1, n + 1):
        if praat_call(tg, "Get label of interval", 1, i) == "sounding":
            t1 = praat_call(tg, "Get start time of interval", 1, i)
            t2 = praat_call(tg, "Get end time of interval", 1, i)
            if t2 - t1 > 0.03:
                spans.append((t1, t2))
    return spans


async def generate_sing(text: str, out_path: str, preset_key: str = DEFAULT_PRESET, fmt: str = "mp3", style: str = "none") -> None:
    if parselmouth is None:
        raise RuntimeError("parselmouth unavailable")
    preset = VOICE_PRESETS.get(preset_key, VOICE_PRESETS[DEFAULT_PRESET])
    src = out_path + ".src.mp3"
    wav = out_path + ".src.wav"
    sang = out_path + ".sang.wav"
    fx = out_path + ".fx.wav"
    music = out_path + ".music.wav"
    communicate = edge_tts.Communicate(text, preset["voice"], rate="-12%", pitch=preset["pitch"])
    await communicate.save(src)
    await _ffmpeg(["-i", src, "-ac", "1", "-ar", "44100", wav])
    snd = parselmouth.Sound(wav)
    duration = snd.get_total_duration()
    manipulation = praat_call(snd, "To Manipulation", 0.01, 60, 700)
    pitch_tier = praat_call("Create PitchTier", "melody", 0.0, duration)
    spans = _sounding_intervals(snd) or [(0.0, duration)]
    for idx, (t1, t2) in enumerate(spans):
        base = SING_SCALE[idx % len(SING_SCALE)]
        t = t1
        while t < t2:
            praat_call(pitch_tier, "Add point", t, float(base))
            t += 0.02
        praat_call(pitch_tier, "Add point", t2 - 0.005, float(base))
    praat_call([manipulation, pitch_tier], "Replace pitch tier")
    resynth = praat_call(manipulation, "Get resynthesis (overlap-add)")
    resynth.save(sang, "WAV")
    filt = preset.get("fx", FLANGER)
    codec = ["-c:a", "libopus", "-b:a", "64k"] if fmt == "ogg" else ["-c:a", "libmp3lame", "-b:a", "128k"]
    if style in MUSIC_STYLES and np is not None:
        await _ffmpeg(["-i", sang, "-af", filt, "-ar", "44100", fx])
        bpm, chords, kind = MUSIC_STYLES[style]
        write_wav(music, make_music(duration + 0.5, bpm, chords, kind))
        await _ffmpeg(["-i", fx, "-i", music, "-filter_complex",
                       "[0:a]volume=1.7[v];[1:a]volume=0.8[m];[v][m]amix=inputs=2:duration=longest:dropout_transition=0",
                       *codec, out_path])
        for p in (fx, music):
            if os.path.exists(p):
                os.remove(p)
    else:
        await _ffmpeg(["-i", sang, "-af", filt, *codec, out_path])
    for p in (src, wav, sang):
        if os.path.exists(p):
            os.remove(p)


async def image_prompt_to_english(prompt: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "You are a photorealistic image prompt generator. Convert the user's request "
                "into a concise, vivid English prompt for a photorealistic image. "
                "Include keywords like 'photorealistic, ultra realistic, highly detailed, "
                "8k, professional photography, natural lighting'. "
                "Return only the English prompt text, nothing else."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    payload = {"model": LLM_MODEL, "messages": messages, "stream": False}
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(LLM_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


async def generate_image(prompt: str) -> bytes:
    en_prompt = await image_prompt_to_english(prompt)
    url = IMAGE_URL.format(prompt=quote(en_prompt))
    async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


async def draw_image(message: Message, prompt: str) -> None:
    sent = await message.answer("🎨 Рисую...")
    try:
        img = await generate_image(prompt)
        await message.answer_photo(BufferedInputFile(img, filename="image.jpg"), caption=f"🎨 {prompt}")
        await sent.delete()
    except Exception as exc:
        await sent.edit_text(f"Не получилось нарисовать: {exc}")


async def sing_reply(message: Message, text: str) -> None:
    sent = await message.answer("🎼 Пою…")
    try:
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            path = f.name
        key = voice_settings.get(message.from_user.id, DEFAULT_PRESET)
        style = music_settings.get(message.from_user.id, "none")
        await generate_sing(text, path, key, fmt="ogg", style=style)
        await message.answer_voice(FSInputFile(path))
        os.remove(path)
        await sent.delete()
    except Exception as exc:
        await sent.edit_text(f"Не получилось спеть: {exc}")


@dp.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(ABOUT_TEXT, reply_markup=main_keyboard())


@dp.message(Command("voice"))
async def voice_menu(message: Message) -> None:
    await message.answer("Голос и музыка для пения:", reply_markup=voice_music_keyboard(message.from_user.id))


@dp.message(Command("music"))
async def music_menu(message: Message) -> None:
    await message.answer("Голос и музыка для пения:", reply_markup=voice_music_keyboard(message.from_user.id))


@dp.message(Command("img"))
async def img_command(message: Message) -> None:
    prompt = (message.text or "")[len("/img"):].strip()
    if not prompt:
        await message.answer("Напиши: /img описание картинки\nНапример: /img закат над морем")
        return
    await draw_image(message, prompt)


@dp.message(F.text == "🎙 Голос")
async def kb_voice(message: Message) -> None:
    await message.answer("Голос и музыка для пения:", reply_markup=voice_music_keyboard(message.from_user.id))


@dp.message(F.text == "🖼 Картинка")
async def kb_image(message: Message) -> None:
    image_mode.add(message.from_user.id)
    await message.answer("Включил режим рисования. Напиши, что нарисовать (или сразу /img описание).")


@dp.message(F.text == "🎼 Песни")
async def kb_sing(message: Message) -> None:
    uid = message.from_user.id
    if uid in sing_mode:
        sing_mode.discard(uid)
        await message.answer("Режим песен выключен. Отвечаю как обычно. 💬")
    else:
        sing_mode.add(uid)
        style = MUSIC_NAMES.get(music_settings.get(uid, "none"), "Без музыки")
        await message.answer(f"🎼 Режим песен включён! Музыка: {style}.\nНапиши любой текст — спою его. Сменить музыку: /music")


@dp.message(F.text == "🎶 Музыка")
async def kb_music(message: Message) -> None:
    await message.answer("Голос и музыка для пения:", reply_markup=voice_music_keyboard(message.from_user.id))


@dp.message(F.text == "🔇 Молчать")
async def kb_voice_off(message: Message) -> None:
    voice_enabled.discard(message.from_user.id)
    sing_mode.discard(message.from_user.id)
    await message.answer("Молчу. Отвечаю только текстом, без голоса и песен. 🤐")


@dp.message(F.text == "🧠 Стереть память")
async def kb_new(message: Message) -> None:
    history.pop(message.from_user.id, None)
    await message.answer("Память стёрта. Начинаем с чистого листа. 🧹")


@dp.message(F.text == "🤖 Кто ты?")
async def kb_about(message: Message) -> None:
    await message.answer(ABOUT_TEXT)


@dp.callback_query(lambda c: c.data and c.data.startswith("voice:"))
async def voice_callback(cq: CallbackQuery) -> None:
    uid = cq.from_user.id
    action = cq.data.split(":", 1)[1]
    if action == "off":
        voice_enabled.discard(uid)
        await cq.message.edit_text("Голос выключен.", reply_markup=voice_music_keyboard(uid))
    elif action in VOICE_PRESETS:
        voice_settings[uid] = action
        voice_enabled.add(uid)
        name = VOICE_PRESETS[action]["name"]
        await cq.message.edit_text(
            f"Выбран голос: {name}. Слушай пример ниже:",
            reply_markup=voice_music_keyboard(uid),
        )
        try:
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
                audio_path = f.name
            await generate_voice("Привет! Это мой голос.", audio_path, action, fmt="ogg")
            await cq.message.answer_voice(FSInputFile(audio_path))
            os.remove(audio_path)
        except Exception:
            pass
    await cq.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("music:"))
async def music_callback(cq: CallbackQuery) -> None:
    uid = cq.from_user.id
    key = cq.data.split(":", 1)[1]
    if key in MUSIC_NAMES:
        music_settings[uid] = key
        await cq.message.edit_text(f"Музыка для пения: {MUSIC_NAMES[key]}", reply_markup=voice_music_keyboard(uid))
    await cq.answer()


@dp.message(Command("new"))
async def clear_history(message: Message) -> None:
    history.pop(message.from_user.id, None)
    await message.answer("История диалога очищена.")


@dp.message(Command("status"))
async def status_cmd(message: Message) -> None:
    uid = message.from_user.id
    voice_state = "вкл" if uid in voice_enabled else "выкл"
    voice_name = VOICE_PRESETS.get(voice_settings.get(uid, DEFAULT_PRESET), {}).get("name", "-")
    sing_state = "вкл" if uid in sing_mode else "выкл"
    await message.answer(
        f"Режимы:\n🎙 Голос: {voice_state} ({voice_name})\n🎼 Песни: {sing_state}\n🧠 Память: {len(memory_facts)} фактов"
    )


@dp.message()
async def chat(message: Message) -> None:
    uid = message.from_user.id
    if uid in image_mode:
        image_mode.discard(uid)
        prompt = (message.text or "").strip()
        if prompt:
            await draw_image(message, prompt)
            return
    if uid in sing_mode:
        text = (message.text or "").strip()
        if text:
            await sing_reply(message, text)
            return
    hist = get_history(uid)
    hist.append({"role": "user", "content": message.text or ""})
    hist = hist[-HISTORY_LIMIT:]
    history[uid] = hist

    sent = await message.answer("Думаю...")

    try:
        reply = await ask_llm(hist)
        if not reply:
            reply = "(пустой ответ от модели)"
        reply = strip_markdown(reply)

        await sent.edit_text(reply)
        hist.append({"role": "assistant", "content": reply})
        history[uid] = hist[-HISTORY_LIMIT:]
        asyncio.create_task(update_memory(hist, reply))

        if uid in voice_enabled:
            try:
                key = voice_settings.get(uid, DEFAULT_PRESET)
                with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
                    audio_path = f.name
                await generate_voice(reply[:300], audio_path, key, fmt="ogg")
                await message.answer_voice(FSInputFile(audio_path))
                os.remove(audio_path)
            except Exception:
                pass
    except httpx.HTTPStatusError as exc:
        await sent.edit_text(f"Ошибка API ({exc.response.status_code}): {exc.response.text[:200]}")
    except Exception as exc:
        await sent.edit_text(f"Ошибка: {exc}")


async def run_polling() -> None:
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


def run_webhook() -> None:
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
    from aiohttp import web

    app = web.Application()

    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    async def serve_app(_: web.Request) -> web.Response:
        return web.FileResponse(
            STATIC_DIR / "index.html",
            headers={"Cache-Control": "no-store, max-age=0"},
        )

    async def api_chat(request: web.Request) -> web.Response:
        if not is_authorized(request):
            return web.json_response({"error": "forbidden"}, status=403)
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "bad json"}, status=400)
        messages = data.get("messages", []) if isinstance(data, dict) else []
        if not messages:
            return web.json_response({"error": "no messages"}, status=400)
        try:
            reply = await ask_llm(messages[-HISTORY_LIMIT:])
            reply = strip_markdown(reply or "")
            asyncio.create_task(update_memory(messages[-HISTORY_LIMIT:], reply))
            return web.json_response({"reply": reply})
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)

    async def api_voice(request: web.Request) -> web.Response:
        if not is_authorized(request):
            return web.json_response({"error": "forbidden"}, status=403)
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "bad json"}, status=400)
        text = (data.get("text") or "").strip()
        preset = data.get("voice") or DEFAULT_PRESET
        if preset not in VOICE_PRESETS:
            preset = DEFAULT_PRESET
        _name = VOICE_PRESETS[preset]["name"]
        fd, path = tempfile.mkstemp(suffix=".ogg")
        os.close(fd)
        try:
            await generate_voice(text, path, preset, fmt="ogg")
            with open(path, "rb") as fh:
                audio = fh.read()
            return web.Response(body=audio, content_type="audio/ogg")
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)
        finally:
            if os.path.exists(path):
                os.remove(path)

    async def api_login(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "bad json"}, status=400)
        password = (data.get("password") or "") if isinstance(data, dict) else ""
        if not check_password(password):
            return web.json_response({"error": "wrong password"}, status=401)
        resp = web.json_response({"ok": True})
        resp.set_cookie(
            "nav_auth",
            SESSION_TOKEN,
            httponly=True,
            secure=True,
            samesite="Lax",
            max_age=60 * 60 * 24 * 365,
        )
        return resp

    async def api_voice_get(request: web.Request) -> web.Response:
        if not is_authorized(request):
            return web.json_response({"error": "forbidden"}, status=403)
        text = (request.query.get("text") or "").strip()[:300]
        if not text:
            return web.json_response({"error": "no text"}, status=400)
        voice_key = request.query.get("voice") or DEFAULT_PRESET
        if voice_key not in VOICE_PRESETS:
            voice_key = DEFAULT_PRESET
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        try:
            await generate_voice(text, path, voice_key, fmt="mp3")
            with open(path, "rb") as fh:
                audio = fh.read()
            return web.Response(body=audio, content_type="audio/mpeg")
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)
        finally:
            if os.path.exists(path):
                os.remove(path)

    async def api_sing_get(request: web.Request) -> web.Response:
        if not is_authorized(request):
            return web.json_response({"error": "forbidden"}, status=403)
        text = (request.query.get("text") or "").strip()[:300]
        if not text:
            return web.json_response({"error": "no text"}, status=400)
        voice_key = request.query.get("voice") or DEFAULT_PRESET
        if voice_key not in VOICE_PRESETS:
            voice_key = DEFAULT_PRESET
        style = request.query.get("style") or "none"
        if style not in MUSIC_STYLES:
            style = "none"
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        try:
            await generate_sing(text, path, voice_key, fmt="mp3", style=style)
            with open(path, "rb") as fh:
                audio = fh.read()
            return web.Response(body=audio, content_type="audio/mpeg")
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)
        finally:
            if os.path.exists(path):
                os.remove(path)

    async def api_me(request: web.Request) -> web.Response:
        if not is_authorized(request):
            return web.json_response({"ok": False}, status=401)
        resp = web.json_response({"ok": True})
        if request.cookies.get("nav_auth") != SESSION_TOKEN:
            resp.set_cookie(
                "nav_auth",
                SESSION_TOKEN,
                httponly=True,
                secure=True,
                samesite="Lax",
                max_age=60 * 60 * 24 * 365,
            )
        return resp

    async def serve_static(request: web.Request) -> web.Response:
        rel = request.match_info.get("path", "")
        target = (STATIC_DIR / rel).resolve()
        try:
            target.relative_to(STATIC_DIR.resolve())
        except ValueError:
            raise web.HTTPNotFound()
        if target.is_file():
            return web.FileResponse(target, headers={"Cache-Control": "no-store"})
        raise web.HTTPNotFound()

    app.router.add_get("/", serve_app)
    app.router.add_get("/app", serve_app)
    app.router.add_post("/api/chat", api_chat)
    app.router.add_post("/api/voice", api_voice)
    app.router.add_post("/api/login", api_login)
    app.router.add_get("/api/voice", api_voice_get)
    app.router.add_get("/api/sing", api_sing_get)
    app.router.add_get("/api/me", api_me)
    app.router.add_get("/{path:.*}", serve_static)

    async def self_ping() -> None:
        if not RENDER_URL:
            return
        url = RENDER_URL.rstrip("/") + "/"
        while True:
            await asyncio.sleep(300)
            try:
                async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                    await client.get(url)
            except Exception:
                pass

    async def on_startup(_: web.Application) -> None:
        await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=False)
        if MINIAPP_URL:
            try:
                await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
            except Exception:
                pass
        asyncio.create_task(self_ping())

    app.on_startup.append(on_startup)

    web.run_app(app, host=HOST, port=PORT)


if __name__ == "__main__":
    if WEBHOOK_URL:
        run_webhook()
    else:
        asyncio.run(run_polling())

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import tempfile
import unicodedata
import wave

# deploy marker: model selector v2
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
MEMORY_BIN_URL = "https://extendsclass.com/api/json-storage/bin/efdadca"
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/")
LLM_URL = f"{LLM_BASE_URL}/chat/completions"
BALANCE_URL = f"{LLM_BASE_URL}/user/balance"

DEFAULT_MODEL_KEY = "deepseek"
MODEL_OPTIONS = [
    {"key": "deepseek", "label": "DeepSeek · универсальная", "provider": "deepseek"},
    {"key": "gpt4o", "label": "GPT-4o mini (OpenAI)", "provider": "openrouter", "model": "openai/gpt-4o-mini"},
    {"key": "gpt41", "label": "GPT-4.1 mini (OpenAI)", "provider": "openrouter", "model": "openai/gpt-4.1-mini"},
    {"key": "gemini", "label": "Gemini 2.5 Flash (Google)", "provider": "openrouter", "model": "google/gemini-2.5-flash"},
    {"key": "claude", "label": "Claude Sonnet 4.5 (Anthropic)", "provider": "openrouter", "model": "anthropic/claude-sonnet-4.5"},
    {"key": "haiku", "label": "Claude Haiku 4.5 (Anthropic)", "provider": "openrouter", "model": "anthropic/claude-haiku-4.5"},
]

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
VISION_MODELS = []
_vm_env = os.getenv("VISION_MODEL", "").strip()
if _vm_env:
    VISION_MODELS.append(_vm_env)
for _vm in (
    "qwen/qwen3.8-27b:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "openrouter/free",
):
    if _vm not in VISION_MODELS:
        VISION_MODELS.append(_vm)
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_CREDITS_URL = "https://openrouter.ai/api/v1/credits"

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
    "male": {
        "name": "Мужской",
        "voice": "ru-RU-DmitryNeural",
        "rate": "-15%",
        "pitch": "+0Hz",
        "fx": "aecho=0.8:0.7:40:0.15",
    },
    "male_low": {
        "name": "Мужской низкий",
        "voice": "ru-RU-DmitryNeural",
        "rate": "-15%",
        "pitch": "-50Hz",
        "fx": "aecho=0.8:0.7:40:0.15",
    },
    "female": {
        "name": "Женский",
        "voice": "ru-RU-SvetlanaNeural",
        "rate": "-15%",
        "pitch": "+0Hz",
        "fx": "aecho=0.8:0.7:40:0.15",
    },
    "bonya": {
        "name": "Боня",
        "voice": "ru-RU-DmitryNeural",
        "rate": "-15%",
        "pitch": "+80Hz",
        "fx": FLANGER,
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
model_settings: dict[int, str] = {}
image_mode: set[int] = set()
sing_mode: set[int] = set()
music_settings: dict[int, str] = {}
song_drafts: dict[int, str] = {}
song_edit: set[int] = set()
voice_edit: set[int] = set()
voice_drafts: dict[int, str] = {}
last_file: dict[int, str] = {}
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


def voice_keyboard(uid: int) -> InlineKeyboardMarkup:
    cur = voice_settings.get(uid, DEFAULT_PRESET)
    rows = []
    items = list(VOICE_PRESETS.items())
    for i in range(0, len(items), 2):
        row = [
            InlineKeyboardButton(
                text=("✅ " if key == cur else "") + data["name"],
                callback_data=f"voice:{key}",
            )
            for key, data in items[i:i + 2]
        ]
        rows.append(row)
    rows.append([InlineKeyboardButton(text="🔇 Выключить голос", callback_data="voice:off")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


MUSIC_NAMES = {
    "none": "Без музыки",
    "pop": "Поп",
    "ballad": "Баллада",
    "rock": "Рок",
    "bassbeat": "Бас + бит",
    "marimba": "Маримба",
    "jazz": "Джаз",
    "country": "Кантри",
    "hiphop": "Хип-хоп",
    "bit": "8-бит",
    "ethnic": "Этно",
    "sad": "Грустный",
    "disco": "Диско",
}


def music_keyboard(uid: int) -> InlineKeyboardMarkup:
    cur = music_settings.get(uid, "none")
    rows = []
    items = list(MUSIC_NAMES.items())
    for i in range(0, len(items), 2):
        rows.append([
            InlineKeyboardButton(
                text=("✅ " if key == cur else "") + data,
                callback_data=f"music:{key}",
            )
            for key, data in items[i:i + 2]
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def voice_music_keyboard(uid: int) -> InlineKeyboardMarkup:
    cur_voice = voice_settings.get(uid, DEFAULT_PRESET)
    cur_music = music_settings.get(uid, "none")
    rows = []
    vitems = list(VOICE_PRESETS.items())
    for i in range(0, len(vitems), 2):
        rows.append([
            InlineKeyboardButton(
                text=("✅ " if key == cur_voice else "") + data["name"],
                callback_data=f"voice:{key}",
            )
            for key, data in vitems[i:i + 2]
        ])
    mitems = list(MUSIC_NAMES.items())
    for i in range(0, len(mitems), 2):
        rows.append([
            InlineKeyboardButton(
                text=("✅ " if key == cur_music else "") + data,
                callback_data=f"music:{key}",
            )
            for key, data in mitems[i:i + 2]
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_keyboard() -> ReplyKeyboardMarkup:
    row1 = [
        KeyboardButton(text="🎙 Голос"),
        KeyboardButton(text="🔇 Молчать"),
        KeyboardButton(text="🎼 Песни"),
        KeyboardButton(text="🎶 Музыка"),
    ]
    row2 = [
        KeyboardButton(text="🤖 Модель"),
        KeyboardButton(text="📊 Статус"),
        KeyboardButton(text="💰 Баланс"),
    ]
    if MINIAPP_URL:
        row2.insert(0, KeyboardButton(text="🚀 Боня", web_app=WebAppInfo(url=MINIAPP_URL)))
    keyboard = [row1, row2]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_history(uid: int) -> list[dict]:
    return history.setdefault(uid, [])


def last_assistant_text(uid: int) -> str:
    for m in reversed(get_history(uid)):
        if m.get("role") == "assistant" and m.get("content"):
            return str(m["content"])
    return ""


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


def clean_tts(text: str) -> str:
    out = []
    for ch in text:
        if ch == "\n":
            out.append(". ")
            continue
        cat = unicodedata.category(ch)
        if cat[0] in ("L", "N") or ch in " .,!?-—:;'\"()":
            out.append(ch)
    return "".join(out).strip()


def extract_text(path: str, name: str) -> str:
    lower = name.lower()
    if lower.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(path)
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:
            return ""
    if lower.endswith(".docx"):
        try:
            import docx
            doc = docx.Document(path)
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception:
            return ""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


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


def resolve_llm(uid: int):
    key = model_settings.get(uid, DEFAULT_MODEL_KEY)
    opt = next((m for m in MODEL_OPTIONS if m["key"] == key), None)
    if opt and opt.get("provider") == "openrouter" and OPENROUTER_API_KEY:
        return OPENROUTER_URL, OPENROUTER_API_KEY, opt["model"]
    return LLM_URL, LLM_API_KEY, LLM_MODEL


def model_keyboard(uid: int) -> InlineKeyboardMarkup:
    cur = model_settings.get(uid, DEFAULT_MODEL_KEY)
    rows = []
    for m in MODEL_OPTIONS:
        mark = "✅ " if m["key"] == cur else ""
        rows.append([InlineKeyboardButton(text=mark + m["label"], callback_data=f"model:{m['key']}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def ask_llm(messages: list[dict], provider=None) -> str:
    url, api_key, model = provider or (LLM_URL, LLM_API_KEY, LLM_MODEL)
    system = SYSTEM_PROMPT
    if memory_facts:
        system += "\n\nЧто ты помнишь о пользователе (учитывай это):\n" + "\n".join(f"- {f}" for f in memory_facts)
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}] + messages,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


async def ask_vision(image_bytes: bytes, question: str) -> str:
    b64 = base64.b64encode(image_bytes).decode()
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    last_exc = None
    async with httpx.AsyncClient(timeout=120) as client:
        for model in VISION_MODELS:
            body = {
                "model": model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question or "Если на изображении есть текст — верни его дословно. Иначе кратко опиши, что на фото."},
                        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
                    ],
                }],
            }
            try:
                resp = await client.post(OPENROUTER_URL, json=body, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue
    raise last_exc if last_exc else RuntimeError("vision failed")


async def load_memory() -> None:
    global memory_facts, history, voice_enabled, voice_settings, model_settings
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(MEMORY_BIN_URL)
            data = resp.json()
        if isinstance(data, dict):
            facts = data.get("facts", [])
            if isinstance(facts, list):
                memory_facts = facts
            hist = data.get("history", {})
            if isinstance(hist, dict):
                history = {int(k): v for k, v in hist.items() if isinstance(v, list)}
            ve = data.get("voice_enabled", [])
            if isinstance(ve, list):
                voice_enabled = {int(x) for x in ve}
            vs = data.get("voice_settings", {})
            if isinstance(vs, dict):
                voice_settings = {int(k): v for k, v in vs.items()}
            ms = data.get("model_settings", {})
            if isinstance(ms, dict):
                model_settings = {int(k): v for k, v in ms.items()}
    except Exception:
        pass


async def push_state() -> None:
    try:
        payload = {
            "facts": memory_facts,
            "history": {str(k): v for k, v in history.items()},
            "voice_enabled": sorted(voice_enabled),
            "voice_settings": {str(k): v for k, v in voice_settings.items()},
            "model_settings": {str(k): v for k, v in model_settings.items()},
        }
        async with httpx.AsyncClient(timeout=30) as client:
            await client.put(MEMORY_BIN_URL, json=payload)
    except Exception:
        pass


async def save_memory(facts: list[str]) -> None:
    global memory_facts
    memory_facts = facts
    await push_state()


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
        await save_memory(facts[:30])
    except Exception:
        pass


async def _tts_save(text: str, voice: str, rate: str, pitch: str, out: str) -> None:
    last = None
    for _attempt in range(2):
        try:
            await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(out)
            if os.path.exists(out) and os.path.getsize(out) > 0:
                return
        except Exception as exc:  # noqa: BLE001
            last = exc
        await asyncio.sleep(0.6)
    try:
        from gtts import gTTS
        await asyncio.to_thread(gTTS(text=text, lang="ru").save, out)
        if os.path.exists(out) and os.path.getsize(out) > 0:
            return
    except Exception as exc:  # noqa: BLE001
        last = exc
    raise last or RuntimeError("tts: no audio")


async def generate_voice(text: str, out_path: str, preset_key: str = DEFAULT_PRESET, fmt: str = "ogg") -> None:
    preset = VOICE_PRESETS.get(preset_key, VOICE_PRESETS[DEFAULT_PRESET])
    src = out_path + ".src.mp3"
    await _tts_save(clean_tts(text) or "…", preset["voice"], preset["rate"], preset["pitch"], src)
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


_N = {
    "C3": 130.81, "D3": 146.83, "E3": 164.81, "F3": 174.61, "G3": 196.00, "A3": 220.00, "B3": 246.94,
    "C4": 261.63, "D4": 293.66, "E4": 329.63, "F4": 349.23, "G4": 392.00, "A4": 440.00, "B4": 493.88,
}
_MAJ = [["C4", "E4", "G4"], ["G3", "B3", "D4"], ["A3", "C4", "E4"], ["F3", "A3", "C4"]]
_MIN = [["A3", "C4", "E4"], ["F3", "A3", "C4"], ["C4", "E4", "G4"], ["G3", "B3", "D4"]]
RICH_STYLES = {"pop": (110, _MAJ, "pop"), "ballad": (72, _MIN, "ballad"), "rock": (132, _MAJ, "rock")}


def _h(freq, dur, harms):
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    return sum(a * np.sin(2 * np.pi * freq * h * t) for h, a in harms)


def _piano(freq, dur):
    sig = _h(freq, dur, ((1, 1.0), (2, 0.5), (3, 0.25), (4, 0.12), (5, 0.06)))
    n = len(sig)
    return sig * np.exp(-np.linspace(0, 4, n)) * np.minimum(1, np.linspace(0, 1, n) * 60)


def _pad2(freq, dur):
    sig = _h(freq, dur, ((1, 1.0), (2, 0.35), (3, 0.15)))
    n = len(sig)
    return sig * np.minimum(1, np.linspace(0, 1, n) * 8) * np.minimum(1, np.linspace(1, 0, n) * 8)


def _bass2(freq, dur):
    sig = _h(freq, dur, ((1, 1.0), (2, 0.5), (3, 0.2)))
    n = len(sig)
    return sig * np.exp(-np.linspace(0, 2.5, n)) * np.minimum(1, np.linspace(0, 1, n) * 80)


def make_rich_music(duration, bpm, prog, kind):
    beat = 60.0 / bpm
    n = int(SR * duration) + SR
    track = np.zeros(n)
    bar = beat * 4
    for i in range(int(np.ceil(duration / bar))):
        chord = prog[i % len(prog)]
        base = int(i * bar * SR)
        for note in chord:
            _add(track, base, _pad2(_N[note], bar * 0.98), 0.12)
        if kind in ("pop", "ballad"):
            pattern = [0, 1, 2, 1, 2, 1, 0, 1]
            for j, idx in enumerate(pattern):
                _add(track, base + int(j * beat / 2 * SR), _piano(_N[chord[idx]] * 2, beat * 0.9), 0.16)
        for j in range(8):
            _add(track, base + int(j * beat / 2 * SR), _bass2(_N[chord[0]] / 2, beat * 0.45), 0.5)
    for b in range(int(np.ceil(duration / beat))):
        pos = int(b * beat * SR)
        bb = b % 4
        if kind == "pop":
            _add(track, pos, _kick(), 0.9)
            if bb in (1, 3):
                _add(track, pos, _snare(), 0.55)
            for off in (0.0, beat / 2):
                _add(track, int((b * beat + off) * SR), _hihat(), 0.22)
        elif kind == "ballad":
            if bb in (0, 2):
                _add(track, pos, _kick(), 0.6)
            if bb in (1, 3):
                _add(track, pos, _snare(), 0.35)
        elif kind == "rock":
            _add(track, pos, _kick(), 0.95)
            if bb in (1, 3):
                _add(track, pos, _snare(), 0.6)
            for off in (0.0, beat / 2):
                _add(track, int((b * beat + off) * SR), _hihat(), 0.25)
    m = float(np.max(np.abs(track))) or 1.0
    return track / m * 0.85


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
    await _tts_save(clean_tts(text) or "…", preset["voice"], "-12%", preset["pitch"], src)
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
    if style in RICH_STYLES and np is not None:
        await _ffmpeg(["-i", sang, "-af", filt, "-ar", "44100", fx])
        bpm, prog, kind = RICH_STYLES[style]
        write_wav(music, make_rich_music(duration + 0.5, bpm, prog, kind))
        await _ffmpeg(["-i", fx, "-i", music, "-filter_complex",
                       "[0:a]volume=1.7[v];[1:a]volume=0.8[m];[v][m]amix=inputs=2:duration=longest:dropout_transition=0",
                       *codec, out_path])
        for p in (fx, music):
            if os.path.exists(p):
                os.remove(p)
    elif style in MUSIC_STYLES and np is not None:
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


async def sing_reply(message: Message, text: str, lyrics: str | None = None) -> None:
    sent = await message.answer("🎼 Готовлю песню…")
    try:
        if not lyrics:
            lyrics = await compose_song(text)
        if not lyrics:
            lyrics = text[:300]
        song_drafts[message.from_user.id] = lyrics
        await sent.edit_text(f"🎼 {lyrics}", reply_markup=song_keyboard())
    except Exception as exc:
        await sent.edit_text(f"Не получилось сочинить: {exc}")


def song_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="▶️ Запуск", callback_data="song:play"),
        InlineKeyboardButton(text="✏️ Доработать", callback_data="song:edit"),
    ]])


def voice_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="▶️ Запуск", callback_data="vtext:play"),
        InlineKeyboardButton(text="✏️ Редактировать", callback_data="vtext:edit"),
    ]])


async def voice_preview(message: Message, text: str) -> None:
    voice_drafts[message.from_user.id] = text
    await message.answer(f"🔊 Озвучу этот текст один-в-один:\n\n{text}", reply_markup=voice_buttons())


SCHEDULE_PROMPT = (
    "Ты — помощник, который разбирает письма от канцелярии монастыря (Киево-Печерская лавра). "
    "Из текста письма извлеки расписание служений. Ответь кратко и структурированно строками:\n"
    "📅 Дата:\n🕐 Время:\n⛪ Место (храм/праздник):\n🕯 Служба:\n👥 Сослужащие (с кем служит архидиакон Евстратий):\n"
    "Если чего-то нет в письме — поставь «—». Не выдумывай. Не добавляй лишнего текста."
)


async def parse_schedule(message: Message, text: str) -> None:
    sent = await message.answer("📄 Разбираю письмо…")
    try:
        reply = await ask_llm([{"role": "user", "content": SCHEDULE_PROMPT + "\n\nПисьмо:\n" + text}])
        await sent.edit_text(strip_markdown(reply or "")[:4000])
    except Exception as exc:
        await sent.edit_text(f"Ошибка разбора: {exc}")


async def compose_song(topic: str) -> str:
    reply = await ask_llm([{
        "role": "user",
        "content": (
            "Сочини короткую весёлую песенку (2-4 строки) на тему: " + topic +
            ". Верни только текст песенки, без пояснений и без кавычек."
        ),
    }])
    return strip_markdown(reply or "").strip()[:300]


async def revise_song(message: Message, instr: str) -> None:
    uid = message.from_user.id
    prev = song_drafts.get(uid, "")
    sent = await message.answer("🎼 Дорабатываю…")
    try:
        reply = await ask_llm([{
            "role": "user",
            "content": (
                "Ты редактор песен. Вот текст песенки:\n" + prev +
                "\n\nЗадача: " + instr +
                "\nИзмени именно то, что просят, остальное сохрани. Верни только новый текст песенки, без пояснений."
            ),
        }])
        lyrics = strip_markdown(reply or "").strip()[:300] or prev
        song_drafts[uid] = lyrics
        await sent.edit_text(f"🎼 {lyrics}", reply_markup=song_keyboard())
    except Exception as exc:
        await sent.edit_text(f"Ошибка: {exc}")


async def voice_reply(message: Message, text: str) -> None:
    sent = await message.answer("🔊 Озвучиваю…")
    try:
        key = voice_settings.get(message.from_user.id, DEFAULT_PRESET)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            path = f.name
        await generate_voice(text[:300], path, key, fmt="ogg")
        await sent.delete()
        await message.answer_voice(FSInputFile(path))
        os.remove(path)
    except Exception as exc:
        await sent.edit_text(f"Не получилось озвучить: {exc}")


@dp.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(ABOUT_TEXT, reply_markup=main_keyboard())


@dp.message(Command("voice"))
async def voice_menu(message: Message) -> None:
    await message.answer("Выбери голос:", reply_markup=voice_keyboard(message.from_user.id))


@dp.message(Command("music"))
async def music_menu(message: Message) -> None:
    await message.answer("Выбери музыку для пения:", reply_markup=music_keyboard(message.from_user.id))


@dp.message(Command("img"))
async def img_command(message: Message) -> None:
    prompt = (message.text or "")[len("/img"):].strip()
    if not prompt:
        await message.answer("Напиши: /img описание картинки\nНапример: /img закат над морем")
        return
    await draw_image(message, prompt)


@dp.message(F.text == "🎙 Голос")
async def kb_voice(message: Message) -> None:
    await message.answer("Выбери голос:", reply_markup=voice_keyboard(message.from_user.id))


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
        await message.answer(f"🎼 Режим песен включён! Музыка: {style}.\nНапиши тему — сочиню песенку и спою её. Сменить музыку: /music")


@dp.message(F.text == "🎶 Музыка")
async def kb_music(message: Message) -> None:
    await message.answer("Выбери музыку для пения:", reply_markup=music_keyboard(message.from_user.id))


@dp.message(F.text == "🤖 Модель")
async def kb_model(message: Message) -> None:
    await message.answer("🤖 Выбери модель ИИ:", reply_markup=model_keyboard(message.from_user.id))


@dp.message(F.text == "📊 Статус")
async def kb_status(message: Message) -> None:
    await status_cmd(message)


@dp.message(F.text == "💰 Баланс")
async def kb_balance(message: Message) -> None:
    await balance_cmd(message)


@dp.message(F.text == "🔇 Молчать")
async def kb_voice_off(message: Message) -> None:
    voice_enabled.discard(message.from_user.id)
    sing_mode.discard(message.from_user.id)
    asyncio.create_task(push_state())
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
        asyncio.create_task(push_state())
        await cq.message.edit_text("Голос выключен.", reply_markup=voice_keyboard(uid))
    elif action in VOICE_PRESETS:
        voice_settings[uid] = action
        voice_enabled.add(uid)
        asyncio.create_task(push_state())
        name = VOICE_PRESETS[action]["name"]
        await cq.message.edit_text(
            f"Выбран голос: {name}. Теперь бот отвечает и текстом, и голосом. Слушай пример:",
            reply_markup=voice_keyboard(uid),
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


@dp.callback_query(lambda c: c.data == "vtext:play")
async def voice_play_cb(cq: CallbackQuery) -> None:
    uid = cq.from_user.id
    text = (voice_drafts.get(uid) or "").strip()
    await cq.answer()
    if not text:
        await cq.message.answer("Нет текста. Напиши текст заново.")
        return
    msg = await cq.message.answer("🔊 Озвучиваю…")
    try:
        key = voice_settings.get(uid, DEFAULT_PRESET)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            path = f.name
        await generate_voice(text[:500], path, key, fmt="ogg")
        await msg.delete()
        await cq.message.answer_voice(FSInputFile(path))
        os.remove(path)
    except Exception as exc:
        await msg.edit_text(f"Не получилось озвучить: {exc}")


@dp.callback_query(lambda c: c.data == "vtext:edit")
async def voice_edit_cb(cq: CallbackQuery) -> None:
    uid = cq.from_user.id
    voice_edit.add(uid)
    await cq.answer()
    await cq.message.answer("✏️ Напиши исправленный текст — озвучу его один-в-один.")


@dp.callback_query(lambda c: c.data and c.data.startswith("music:"))
async def music_callback(cq: CallbackQuery) -> None:
    uid = cq.from_user.id
    key = cq.data.split(":", 1)[1]
    if key in MUSIC_NAMES:
        music_settings[uid] = key
        await cq.message.edit_text(f"Музыка для пения: {MUSIC_NAMES[key]}", reply_markup=music_keyboard(uid))
    await cq.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("model:"))
async def model_callback(cq: CallbackQuery) -> None:
    uid = cq.from_user.id
    key = cq.data.split(":", 1)[1]
    opt = next((m for m in MODEL_OPTIONS if m["key"] == key), None)
    if opt:
        model_settings[uid] = key
        asyncio.create_task(push_state())
        await cq.message.edit_text(
            f"✅ Готово! Теперь отвечаю моделью: {opt['label']}",
            reply_markup=model_keyboard(uid),
        )
    await cq.answer()


@dp.callback_query(lambda c: c.data == "song:play")
async def song_play(cq: CallbackQuery) -> None:
    uid = cq.from_user.id
    lyrics = song_drafts.get(uid)
    await cq.answer()
    if not lyrics:
        await cq.message.answer("Нет текста для песни. Напиши тему заново.")
        return
    msg = await cq.message.answer("🎼 Пою…")
    try:
        key = voice_settings.get(uid, DEFAULT_PRESET)
        style = music_settings.get(uid, "none")
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            path = f.name
        await generate_sing(lyrics, path, key, fmt="ogg", style=style)
        await msg.delete()
        await cq.message.answer_voice(FSInputFile(path))
        os.remove(path)
    except Exception as exc:
        await msg.edit_text(f"Не получилось спеть: {exc}")


@dp.callback_query(lambda c: c.data == "song:edit")
async def song_edit_cb(cq: CallbackQuery) -> None:
    song_edit.add(cq.from_user.id)
    await cq.answer()
    await cq.message.answer("✏️ Напиши, что доработать (например: «сделай длиннее», «добавь про море»).")


@dp.message(Command("new"))
async def clear_history(message: Message) -> None:
    history.pop(message.from_user.id, None)
    last_file.pop(message.from_user.id, None)
    await message.answer("История диалога очищена.")


@dp.message(Command("model"))
async def model_cmd(message: Message) -> None:
    await message.answer("🤖 Выбери модель ИИ:", reply_markup=model_keyboard(message.from_user.id))


@dp.message(Command("status"))
async def status_cmd(message: Message) -> None:
    uid = message.from_user.id
    voice_state = "вкл" if uid in voice_enabled else "выкл"
    voice_name = VOICE_PRESETS.get(voice_settings.get(uid, DEFAULT_PRESET), {}).get("name", "-")
    sing_state = "вкл" if uid in sing_mode else "выкл"
    vision_state = "вкл" if OPENROUTER_API_KEY else "выкл (нет ключа)"
    model_name = next((m["label"] for m in MODEL_OPTIONS if m["key"] == model_settings.get(uid, DEFAULT_MODEL_KEY)), "DeepSeek")
    await message.answer(
        f"Режимы:\n🎙 Голос: {voice_state} ({voice_name})\n🎼 Песни: {sing_state}\n🤖 Модель: {model_name}\n🧠 Память: {len(memory_facts)} фактов\n👁 Зрение: {vision_state}"
    )


@dp.message(Command("balance"))
async def balance_cmd(message: Message) -> None:
    uid = message.from_user.id
    cur_key = model_settings.get(uid, DEFAULT_MODEL_KEY)
    cur_opt = next((m for m in MODEL_OPTIONS if m["key"] == cur_key), None)
    cur_label = cur_opt["label"] if cur_opt else cur_key
    sent = await message.answer("💰 Проверяю баланс…")
    lines = [f"🤖 Текущая модель: {cur_label}"]
    is_or = bool(cur_opt and cur_opt.get("provider") == "openrouter")

    if LLM_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(BALANCE_URL, headers={"Authorization": f"Bearer {LLM_API_KEY}"})
                resp.raise_for_status()
                data = resp.json()
            infos = data.get("balance_infos") or []
            mark = "" if is_or else "   ← выбранная модель"
            if infos:
                for i in infos:
                    lines.append(f"🟦 DeepSeek: {i.get('total_balance', '?')} {i.get('currency', '')}{mark}".strip())
            else:
                lines.append(f"🟦 DeepSeek: нет данных{mark}")
        except Exception:
            lines.append("🟦 DeepSeek: не удалось узнать")
    else:
        lines.append("🟦 DeepSeek: нет ключа")

    if OPENROUTER_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    OPENROUTER_CREDITS_URL,
                    headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                )
                resp.raise_for_status()
                d = resp.json().get("data", {}) or {}
            total = float(d.get("total_credits", 0) or 0)
            used = float(d.get("total_usage", 0) or 0)
            mark = "   ← выбранная модель" if is_or else ""
            lines.append(f"🟪 OpenRouter (GPT/Gemini/Claude): ${total - used:.2f} (потрачено ${used:.2f}){mark}")
        except Exception:
            lines.append("🟪 OpenRouter: не удалось узнать")
    else:
        lines.append("🟪 OpenRouter: нет ключа")

    await sent.edit_text("\n".join(lines))


@dp.message(F.document)
async def handle_document(message: Message) -> None:
    doc = message.document
    sent = await message.answer("📄 Читаю файл…")
    try:
        name = doc.file_name or "file"
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, name)
            await bot.download(doc, destination=path)
            text = extract_text(path, name)
        if not text.strip():
            await sent.edit_text("Не удалось извлечь текст из файла 😔 (поддерживаю txt, pdf, docx)")
            return
        text = text[:8000]
        last_file[message.from_user.id] = text
        question = (message.caption or "").strip() or "Кратко перескажи, что в этом файле."
        reply = await ask_llm([{"role": "user", "content": f"Содержимое файла:\n{text}\n\nВопрос: {question}"}])
        await sent.edit_text(strip_markdown(reply or "")[:4000])
    except Exception as exc:
        await sent.edit_text(f"Ошибка чтения файла: {exc}")


@dp.message(F.photo)
async def handle_photo(message: Message) -> None:
    if not OPENROUTER_API_KEY:
        await message.answer("Картинки пока не настроены (нет ключа зрения).")
        return
    caption = (message.caption or "").strip()
    caption_low = caption.lower()
    ocr = any(w in caption_low for w in ("текст", "распознай", "розпізнай", "прочитай", "прочти", "перепиши", "ocr"))
    sent = await message.answer("📷 Читаю текст…" if ocr else "👁 Смотрю…")
    try:
        photo = message.photo[-1]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "photo.jpg")
            await bot.download(photo, destination=path)
            with open(path, "rb") as f:
                data = f.read()
        if ocr:
            question = (
                "Распознай ВЕСЬ текст на изображении и верни только этот текст, "
                "без описаний и комментариев. Сохрани порядок строк и знаки препинания."
            )
        else:
            question = caption
        reply = await ask_vision(data, question)
        reply = strip_markdown(reply or "").strip()
        await sent.edit_text(reply[:4000])
        uid = message.from_user.id
        hist = get_history(uid)
        note = ("[фото, распознанный текст]\n" if ocr else "[фото]\n") + (caption or "")
        hist.append({"role": "user", "content": note.strip()})
        hist.append({"role": "assistant", "content": reply})
        history[uid] = hist[-HISTORY_LIMIT:]
        asyncio.create_task(push_state())
    except Exception as exc:
        await sent.edit_text(f"Не получилось посмотреть: {exc}")


@dp.message()
async def chat(message: Message) -> None:
    uid = message.from_user.id
    if uid in image_mode:
        image_mode.discard(uid)
        prompt = (message.text or "").strip()
        if prompt:
            await draw_image(message, prompt)
            return
    if uid in song_edit:
        song_edit.discard(uid)
        instr = (message.text or "").strip()
        if instr:
            await revise_song(message, instr)
        return
    if uid in sing_mode:
        text = (message.text or "").strip()
        if text:
            await sing_reply(message, text)
            return
    if uid in voice_edit:
        voice_edit.discard(uid)
        text = (message.text or "").strip()
        if text:
            await voice_preview(message, text)
        return
    text0 = (message.text or "").strip()
    tl = text0.lower()
    if song_drafts.get(uid) and any(w in tl for w in ("доработ", "измен", "передел", "поправ", "допиши", "добавь")):
        await revise_song(message, text0)
        return
    if any(w in tl for w in ("нарисуй", "намалюй", "сгенерируй картинку", "згенеруй картинку", "намалюй картинку")):
        await draw_image(message, text0)
        return
    if any(w in tl for w in ("спой", "спеть", "песн")):
        prev = last_assistant_text(uid)
        ref = any(w in tl for w in ("его", "её", "ее", "ней", "него", "неё", "это", "этот", "эту", "эти", "тот", "ту", "стих"))
        bare = tl.strip(" !?.,") in ("спой", "спеть", "спой пожалуйста", "спой его", "спой это")
        if prev and (ref or bare):
            await sing_reply(message, text0, lyrics=prev)
        else:
            await sing_reply(message, text0)
        return
    if "озвуч" in tl:
        await voice_preview(message, text0)
        return
    if any(w in tl for w in ("разбери письмо", "разбери лист", "розбери лист", "разбери расписание", "разбери розклад", "канцеляр", "розклад служ", "расписание служ")):
        await parse_schedule(message, text0)
        return
    hist = get_history(uid)
    hist.append({"role": "user", "content": message.text or ""})
    hist = hist[-HISTORY_LIMIT:]
    history[uid] = hist

    sent = await message.answer("Думаю...")

    try:
        msgs = hist
        ctx = last_file.get(uid)
        if ctx:
            msgs = [{"role": "user", "content": "Файл пользователя (расписание/документ):\n" + ctx[:6000]}] + hist
        try:
            reply = await ask_llm(msgs, resolve_llm(uid))
        except Exception:
            if model_settings.get(uid, DEFAULT_MODEL_KEY) != DEFAULT_MODEL_KEY:
                model_settings[uid] = DEFAULT_MODEL_KEY
                asyncio.create_task(push_state())
                reply = "⚠️ Выбранная модель недоступна (нет доступа/кредитов). Отвечаю DeepSeek.\n\n" + await ask_llm(msgs)
            else:
                raise
        if not reply:
            reply = "(пустой ответ от модели)"
        reply = strip_markdown(reply)

        await sent.edit_text(reply)
        hist.append({"role": "assistant", "content": reply})
        history[uid] = hist[-HISTORY_LIMIT:]
        asyncio.create_task(push_state())
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
        if style not in MUSIC_STYLES and style not in RICH_STYLES:
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
        await load_memory()
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

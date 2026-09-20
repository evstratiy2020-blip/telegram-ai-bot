import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import tempfile

# deploy marker: songs button
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
    "кратко, понятно и по делу. "
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

VOICE_PRESETS = {
    "1": ("Боня", "ru-RU-DmitryNeural", "-20%", "+80Hz", FLANGER),
}
DEFAULT_PRESET = "1"

IMAGE_URL = "https://image.pollinations.ai/prompt/{prompt}?width=1024&height=1024&enhance=true&nologo=true"

HISTORY_LIMIT = 20

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

history: dict[int, list[dict]] = {}
voice_enabled: set[int] = set()
voice_settings: dict[int, str] = {}
image_mode: set[int] = set()
sing_mode: set[int] = set()


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
            InlineKeyboardButton(text=name, callback_data=f"voice:{key}")
            for key, (name, *_rest) in items[i:i + 2]
        ]
        rows.append(row)
    rows.append([InlineKeyboardButton(text="🔇 Выключить голос", callback_data="voice:off")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_keyboard() -> ReplyKeyboardMarkup:
    row = [
        KeyboardButton(text="🎙 Голос"),
        KeyboardButton(text="🔇 Молчать"),
        KeyboardButton(text="🎼 Песни"),
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
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(LLM_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


async def generate_voice(text: str, out_path: str, voice: str, rate: str, pitch: str, audio_filter: str) -> None:
    mp3_path = out_path + ".mp3"
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(mp3_path)

    cmd = [
        FFMPEG, "-y", "-i", mp3_path,
        "-af", audio_filter,
        "-c:a", "libopus", "-b:a", "64k",
        out_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    if os.path.exists(mp3_path):
        os.remove(mp3_path)


async def _ffmpeg(args: list[str]) -> None:
    proc = await asyncio.create_subprocess_exec(
        FFMPEG, "-y", *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()


async def generate_voice_mp3(text: str, out_path: str, voice: str, rate: str, pitch: str, audio_filter: str) -> None:
    src = out_path + ".src.mp3"
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(src)
    await _ffmpeg(["-i", src, "-af", audio_filter, "-c:a", "libmp3lame", "-b:a", "96k", out_path])
    if os.path.exists(src):
        os.remove(src)


SING_SCALE = [262, 294, 330, 294, 392, 330, 294, 262, 330, 294, 262, 220]


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


async def generate_sing(text: str, out_path: str, voice: str, pitch: str, audio_filter: str, fmt: str = "mp3") -> None:
    if parselmouth is None:
        raise RuntimeError("parselmouth unavailable")
    src = out_path + ".src.mp3"
    wav = out_path + ".src.wav"
    sang = out_path + ".sang.wav"
    communicate = edge_tts.Communicate(text, voice, rate="-12%", pitch=pitch)
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
    codec = ["-c:a", "libopus", "-b:a", "64k"] if fmt == "ogg" else ["-c:a", "libmp3lame", "-b:a", "128k"]
    await _ffmpeg(["-i", sang, "-af", audio_filter, *codec, out_path])
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
        _name, voice, _rate, pitch, audio_filter = VOICE_PRESETS[DEFAULT_PRESET]
        await generate_sing(text, path, voice, pitch, audio_filter, fmt="ogg")
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
    voice_settings[message.from_user.id] = DEFAULT_PRESET
    voice_enabled.add(message.from_user.id)
    await message.answer("Включил голос. Теперь отвечаю голосом. 🎙")


@dp.message(Command("img"))
async def img_command(message: Message) -> None:
    prompt = (message.text or "")[len("/img"):].strip()
    if not prompt:
        await message.answer("Напиши: /img описание картинки\nНапример: /img закат над морем")
        return
    await draw_image(message, prompt)


@dp.message(F.text == "🎙 Голос")
async def kb_voice(message: Message) -> None:
    voice_settings[message.from_user.id] = DEFAULT_PRESET
    voice_enabled.add(message.from_user.id)
    await message.answer("Включил голос. Теперь отвечаю голосом. 🎙")


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
        await message.answer("🎼 Режим песен включён! Напиши любой текст — спою его голосом Бони.")


@dp.message(F.text == "🔇 Молчать")
async def kb_voice_off(message: Message) -> None:
    voice_enabled.discard(message.from_user.id)
    await message.answer("Молчу. Буду отвечать только текстом. 🤐")


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
        await cq.message.edit_text("Голос выключен.", reply_markup=voice_keyboard())
    elif action in VOICE_PRESETS:
        voice_settings[uid] = action
        voice_enabled.add(uid)
        name, voice, rate, pitch, audio_filter = VOICE_PRESETS[action]
        await cq.message.edit_text(
            f"Выбран голос: {name}. Слушай пример ниже:",
            reply_markup=voice_keyboard(),
        )
        try:
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
                audio_path = f.name
            await generate_voice("Привет! Это мой голос.", audio_path, voice, rate, pitch, audio_filter)
            await cq.message.answer_voice(FSInputFile(audio_path))
            os.remove(audio_path)
        except Exception:
            pass
    await cq.answer()


@dp.message(Command("new"))
async def clear_history(message: Message) -> None:
    history.pop(message.from_user.id, None)
    await message.answer("История диалога очищена.")


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

        if uid in voice_enabled:
            try:
                key = voice_settings.get(uid, DEFAULT_PRESET)
                _name, voice, rate, pitch, audio_filter = VOICE_PRESETS[key]
                with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
                    audio_path = f.name
                await generate_voice(reply, audio_path, voice, rate, pitch, audio_filter)
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
        _name, voice, rate, pitch, audio_filter = VOICE_PRESETS[preset]
        fd, path = tempfile.mkstemp(suffix=".ogg")
        os.close(fd)
        try:
            await generate_voice(text, path, voice, rate, pitch, audio_filter)
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
        text = (request.query.get("text") or "").strip()[:600]
        if not text:
            return web.json_response({"error": "no text"}, status=400)
        _name, voice, rate, pitch, audio_filter = VOICE_PRESETS[DEFAULT_PRESET]
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        try:
            await generate_voice_mp3(text, path, voice, rate, pitch, audio_filter)
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
        _name, voice, _rate, pitch, audio_filter = VOICE_PRESETS[DEFAULT_PRESET]
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        try:
            await generate_sing(text, path, voice, pitch, audio_filter, fmt="mp3")
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

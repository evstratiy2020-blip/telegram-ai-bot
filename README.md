# Telegram ИИ-бот (DeepSeek + облако 24/7)

Бот отвечает в Telegram через API DeepSeek (модель `deepseek-chat`).
Благодаря OpenAI-совместимому API можно переключиться на любой провайдер
(DeepSeek, Groq, OpenAI и т.д.), поменяв `LLM_BASE_URL`/`LLM_MODEL`.

## 1. Получить ключ DeepSeek
1. Зайди на https://platform.deepseek.com и зарегистрируйся.
2. **API Keys** → **Create new API key** → скопируй ключ (начинается с `sk-`).
3. Пополни небольшой баланс (DeepSeek очень дешёвый) — бесплатного тарифа у него нет.

## 2. Развернуть в облаке (Hugging Face Spaces, бесплатно)
1. Зарегистрируйся на https://huggingface.co.
2. **New Space** → SDK: **Docker** → Space: **Blank** → Public.
3. Залей файлы: `bot.py`, `requirements.txt`, `Dockerfile`.

## 3. Переменные окружения (Settings → Variables and secrets)
| Имя | Значение |
|-----|----------|
| `BOT_TOKEN` | токен бота от @BotFather |
| `LLM_API_KEY` | ключ `sk-...` из DeepSeek |
| `LLM_MODEL` | `deepseek-chat` |
| `LLM_BASE_URL` | `https://api.deepseek.com` |
| `WEBHOOK_URL` | `https://ИМЯ-Space.hf.space/webhook` |
| `WEBHOOK_PATH` | `/webhook` |
| `PORT` | `7860` |

## 4. Локальный запуск (проверка)
```bash
pip install -r requirements.txt
python bot.py
```
Без `WEBHOOK_URL` бот работает через long polling.

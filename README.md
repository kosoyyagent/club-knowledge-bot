# club-knowledge-bot

ИИ-бот для Telegram-чата клуба: отвечает по базе знаний, чистит спам, зовёт админа когда не уверен.

- База знаний — обычный `knowledge.md` (правила, расписание, FAQ) — правится без кода.
- Ответы через OpenAI-compatible API (OpenRouter, DeepSeek, Yandex и т.д.).
- Антиспам: внешние ссылки/реклама в группе удаляются, нарушитель получает предупреждение.
- Не нашёл ответа — пишет участнику и пересылает вопрос админу (ADMIN_ID).
- Webhook для PaaS (Render) или polling: `python app.py --poll`.

## Env
TG_TOKEN, WEBHOOK_SECRET, ADMIN_ID, OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL, PORT

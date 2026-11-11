"""
ИИ-бот для Telegram-чата клуба: ответы по базе знаний + антиспам.
Демо под заказ FL.ru #5528900.

- Ответы по базе знаний (knowledge.md) через OpenAI-compatible API (OpenRouter и т.п.)
- Не уверен / нет ответа -> пишет что зовёт админа и шлёт админу уведомление
- Антиспам в группах: ссылки/invite-ссылки/реклама от не-админов -> удаление + предупреждение
- Webhook-режим для любого PaaS (Render и т.п.) или polling локально:  python app.py --poll
"""
import os, re, json, requests
from flask import Flask, request, jsonify

TOKEN   = os.environ.get('TG_TOKEN', '')
API     = 'https://api.telegram.org/bot' + TOKEN
SECRET  = os.environ.get('WEBHOOK_SECRET', 'wh')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '0') or 0)

OPENAI_BASE_URL = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
OPENAI_API_KEY  = os.environ.get('OPENAI_API_KEY', '')
OPENAI_MODEL    = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')

KB = open(os.path.join(os.path.dirname(__file__), 'knowledge.md'), encoding='utf-8').read()

SYSTEM = ('Ты — бот-ассистент платного клуба «Мастерская». Отвечаешь участникам '
          'строго по базе знаний ниже, коротко и по делу, на русском. '
          'Если ответа в базе нет или не уверен — ответь ровно одним словом: ADMIN.\n\n'
          'БАЗА ЗНАНИЙ:\n' + KB)

SPAM_RE = re.compile(
    r'(t\.me/|telegram\.me/|http[s]?://|www\.|заработ|крипт|инвестиц|казино|подписчис)',
    re.I)

app = Flask(__name__)


def tg(method, **kw):
    r = requests.post(API + '/' + method, json=kw, timeout=20)
    return r.json() if r.headers.get('content-type', '').startswith('application/json') else {}


def llm_answer(text):
    if not OPENAI_API_KEY:
        return None
    try:
        r = requests.post(OPENAI_BASE_URL.rstrip('/') + '/chat/completions',
            headers={'Authorization': 'Bearer ' + OPENAI_API_KEY},
            json={'model': OPENAI_MODEL,
                  'messages': [{'role': 'system', 'content': SYSTEM},
                               {'role': 'user', 'content': text}],
                  'temperature': 0.3, 'max_tokens': 600, 'stream': False},
            timeout=60)
        r.raise_for_status()
        return r.json()['choices'][0]['message']['content'].strip()
    except Exception:
        return None


def call_admin(chat_id, text):
    tg('sendMessage', chat_id=chat_id,
       text='Не нашёл точного ответа в базе — передал вопрос администратору, ответит лично.')
    if ADMIN_ID:
        tg('sendMessage', chat_id=ADMIN_ID,
           text='Вопрос без ответа из базы (chat %s):\n%s' % (chat_id, text[:500]))


def handle_message(m):
    chat_id = m['chat']['id']
    text = (m.get('text') or '').strip()
    is_group = m['chat']['type'] in ('group', 'supergroup')
    uid = m.get('from', {}).get('id', 0)
    if not text:
        return

    # антиспам в группе (админов не трогаем)
    if is_group and SPAM_RE.search(text):
        # не удаляем, если ссылка на сам клуб или команда
        if not text.startswith('/'):
            tg('deleteMessage', chat_id=chat_id, message_id=m['message_id'])
            tg('sendMessage', chat_id=chat_id,
               text='Сообщение удалено: реклама и внешние ссылки в клубе запрещены (п.2 правил).')
            return

    if text.startswith('/'):
        cmd = text.split('@')[0].split()[0].lower()
        if cmd == '/start':
            tg('sendMessage', chat_id=chat_id,
               text='Привет! Я ассистент клуба. Отвечаю на вопросы по базе знаний '
                    '(правила, расписание, подписка). Спросите что-нибудь — /help для команд.')
        elif cmd == '/help':
            tg('sendMessage', chat_id=chat_id,
               text='Просто напишите вопрос — отвечу по базе знаний клуба.\n'
                    '/records — записи эфиров\n/rules — правила чата\n'
                    'Если не знаю ответа — позову администратора.')
        elif cmd == '/records':
            tg('sendMessage', chat_id=chat_id,
               text='Записи эфиров: закреплённое сообщение в чате клуба. '
                    'Эфиры каждый четверг 19:00 МСК, разборы — вторник 18:00 МСК.')
        elif cmd == '/rules':
            tg('sendMessage', chat_id=chat_id,
               text='Правила: уважение, без рекламы и внешних ссылок, вопросы — в чат.')
        return

    # в группе отвечаем только на обращения к боту или reply ему
    if is_group:
        to_me = ('@' in text and m.get('entities')) or \
                (m.get('reply_to_message', {}).get('from', {}).get('id') == _bot_id())
        if '@sticker_commenter_k_bot' not in text and not to_me and not text.endswith('?'):
            return

    ans = llm_answer(text)
    if not ans or ans.upper().startswith('ADMIN'):
        call_admin(chat_id, text)
    else:
        tg('sendMessage', chat_id=chat_id, text=ans,
           reply_to_message_id=m['message_id'] if is_group else None)


_bot_cache = {}
def _bot_id():
    if 'id' not in _bot_cache:
        try:
            _bot_cache['id'] = tg('getMe')['result']['id']
        except Exception:
            _bot_cache['id'] = 0
    return _bot_cache['id']


@app.route('/')
def index():
    return 'club-knowledge-bot alive'

@app.route('/tg/' + SECRET, methods=['POST'])
def webhook():
    upd = request.get_json(force=True, silent=True) or {}
    m = upd.get('message') or upd.get('edited_message')
    if m:
        handle_message(m)
    return jsonify(ok=True)


if __name__ == '__main__':
    import sys
    if '--poll' in sys.argv:
        off = 0
        print('polling...')
        while True:
            try:
                for u in tg('getUpdates', offset=off, timeout=40).get('result', []):
                    off = u['update_id'] + 1
                    if u.get('message'):
                        handle_message(u['message'])
            except Exception as e:
                print('poll err', e)
    else:
        app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

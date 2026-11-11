# Telegram as a Chat UI — Setup Guide

Use Telegram as a lightweight chat interface for Cerebro. Instead of building a custom frontend, you get a native mobile + desktop app with push notifications for free.

---

## 1. Create Your Bot

1. Open Telegram and search for **[@BotFather](https://t.me/botfather)**.
2. Send `/newbot`.
3. Follow the prompts — pick a **name** (display name) and a **username** (must end in `bot`, e.g. `cerebro_assistant_bot`).
4. BotFather replies with your **API token**:
   ```
   123456789:ABCdefGhIjKlMnOpQrStUvWxYz
   ```
5. Save this token — you'll need it in your `.env`.

### Optional: Customize Your Bot

While still in BotFather, run these to polish the experience:

| Command           | What it does                      |
| ----------------- | --------------------------------- |
| `/setdescription` | Bio shown before a user starts    |
| `/setabouttext`   | Short text in the bot's profile   |
| `/setuserpic`     | Upload a profile photo            |
| `/setcommands`    | Define the `/` command menu       |

---

## 2. Get Your Chat ID

You need your personal `chat_id` so the bot knows where to send messages.

1. Start a conversation with your bot (hit **Start** in Telegram).
2. Send any message, e.g. `hello`.
3. In your browser, open:
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
4. Find `"chat": { "id": 123456789 }` in the JSON response — that's your `chat_id`.

> **Tip:** For a group chat, add the bot to the group, send a message, then check `getUpdates`. Group chat IDs are negative numbers.

---

## 3. Add Credentials to `.env`

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIjKlMnOpQrStUvWxYz
TELEGRAM_CHAT_ID=123456789
```

---

## 4. Send Messages (Minimal Example)

### Using `requests` (simplest)

```python
import os
import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
API_URL = f"https://api.telegram.org/bot{TOKEN}"


def send_message(text: str, parse_mode: str = "Markdown") -> dict:
    """Send a text message to the configured Telegram chat."""
    response = requests.post(
        f"{API_URL}/sendMessage",
        json={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": parse_mode,
        },
    )
    return response.json()


# Example
send_message("🧠 *Cerebro* is online.")
```

### Using `python-telegram-bot` (full-featured)

```bash
pip install python-telegram-bot
```

```python
import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Cerebro is ready. Send me anything.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    # --- Hook into your Cerebro logic here ---
    reply = f"You said: {user_text}"
    # ------------------------------------------

    await update.message.reply_text(reply)


app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Bot is polling...")
app.run_polling()
```

Run it:

```bash
python bot.py
```

Now open Telegram, message your bot, and it replies.

---

## 5. Receive Messages via Webhook (Production)

Polling works for dev, but for production use a **webhook** so Telegram pushes updates to your server.

### Set the Webhook

```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-domain.com/api/telegram/webhook"}'
```

### Handle It in FastAPI

```python
from fastapi import FastAPI, Request

app = FastAPI()


@app.post("/api/telegram/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    message = data.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if text and chat_id:
        # Process the incoming message through Cerebro
        reply = process_with_cerebro(text)
        await send_reply(chat_id, reply)

    return {"ok": True}
```

> **Requirements:** Your server must be reachable via HTTPS with a valid SSL certificate. For local dev, use [ngrok](https://ngrok.com) to tunnel.

---

## 6. Rich UI Patterns

Telegram supports more than plain text — use these to build a proper chat UI experience.

### Inline Keyboard Buttons

```python
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

keyboard = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("📚 Review", callback_data="review"),
        InlineKeyboardButton("📝 Add Note", callback_data="add_note"),
    ],
    [
        InlineKeyboardButton("📊 Stats", callback_data="stats"),
    ],
])

await update.message.reply_text("What do you want to do?", reply_markup=keyboard)
```

### Handle Button Presses

```python
from telegram.ext import CallbackQueryHandler


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Acknowledge the press

    if query.data == "review":
        await query.edit_message_text("Starting review session...")
    elif query.data == "add_note":
        await query.edit_message_text("Send me the note content:")
    elif query.data == "stats":
        await query.edit_message_text("📊 You reviewed 42 cards today.")


app.add_handler(CallbackQueryHandler(button_handler))
```

### Formatted Messages

Telegram supports Markdown and HTML formatting:

```python
# MarkdownV2 (escape special chars with \)
await update.message.reply_text(
    "📖 *Topic:* Neural Networks\n"
    "🔁 *Next Review:* Tomorrow\n"
    "💪 *Strength:* 85%",
    parse_mode="Markdown",
)
```

### Send Documents / Images

```python
# Send a file
await context.bot.send_document(chat_id=CHAT_ID, document=open("export.pdf", "rb"))

# Send a photo
await context.bot.send_photo(chat_id=CHAT_ID, photo=open("chart.png", "rb"))
```

---

## 7. Security: Lock Down Your Bot

Only allow messages from your own account:

```python
ALLOWED_USERS = {int(os.getenv("TELEGRAM_CHAT_ID"))}


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Unauthorized.")
        return

    # ... process message
```

---

## 8. Quick Reference — Useful Bot API Endpoints

All endpoints are `POST https://api.telegram.org/bot<TOKEN>/<method>`.

| Method              | Purpose                        |
| ------------------- | ------------------------------ |
| `sendMessage`       | Send a text message            |
| `sendPhoto`         | Send an image                  |
| `sendDocument`      | Send a file                    |
| `setWebhook`        | Register a webhook URL         |
| `deleteWebhook`     | Remove the webhook (use polling) |
| `getUpdates`        | Poll for new messages          |
| `getMe`             | Verify your bot token          |
| `sendChatAction`    | Show "typing..." indicator     |

Full API docs: [https://core.telegram.org/bots/api](https://core.telegram.org/bots/api)

---

## TL;DR

```
1. /newbot  via @BotFather  →  get TOKEN
2. Message your bot          →  get CHAT_ID from /getUpdates
3. Add both to .env
4. Use python-telegram-bot for bidirectional chat
5. Lock it to your user ID
6. Ship it 🚀
```

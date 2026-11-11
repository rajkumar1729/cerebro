"""Telegram interface for persisted, LLM-evaluated Obsidian review sessions."""
from __future__ import annotations

import asyncio
import datetime
import os
from zoneinfo import ZoneInfo
from typing import Any

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, ApplicationBuilder, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters,
)

from app.client.db.pg_client import PostgreSQLClient
from app.config import telegram_config
from app.logging_config import setup_logging
from app.repository.note_repository import NoteRepository
from app.service.review_service import ReviewService

logger = setup_logging()
TIMEZONE = ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Kolkata"))


class TelegramClient:
    """Runs a polling bot; Telegram sessions are persisted with PostgreSQL."""

    def __init__(self, review_service: ReviewService | None = None):
        self.config = telegram_config()
        if not self.config.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        self.db = None
        if review_service is None:
            self.db = PostgreSQLClient()
            self.review_service = ReviewService(NoteRepository(self.db))
        else:
            self.review_service = review_service
        self.sessions: dict[int, dict[str, Any]] = {}
        self.app: Application = ApplicationBuilder().token(self.config.telegram_bot_token).post_init(self._post_init).build()
        self._register_handlers()
        self._register_jobs()

    def _register_handlers(self) -> None:
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("topics", self.topics))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CallbackQueryHandler(self.handle_topic, pattern=r"^topic_\d+$"))
        self.app.add_handler(CallbackQueryHandler(self.handle_pick, pattern=r"^pick_\d+$"))
        self.app.add_handler(CallbackQueryHandler(self.handle_submit, pattern=r"^submit$"))
        self.app.add_handler(CallbackQueryHandler(self.handle_answer_mode, pattern=r"^mode_(text|voice)$"))
        self.app.add_handler(CallbackQueryHandler(self.handle_next, pattern=r"^next$"))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        self.app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, self.handle_voice))

    def _register_jobs(self) -> None:
        if self.app.job_queue is None:
            logger.warning("Telegram JobQueue is unavailable; install python-telegram-bot[job-queue]")
            return
        try:
            hour, minute = map(int, self.config.reminder_time.split(":"))
            reminder_time = datetime.time(hour=hour, minute=minute, tzinfo=TIMEZONE)
        except ValueError:
            reminder_time = datetime.time(hour=9, minute=0, tzinfo=TIMEZONE)
        self.app.job_queue.run_daily(self._morning_task, time=reminder_time, name="daily_due_review")

    async def _post_init(self, application: Application) -> None:
        await application.bot.set_my_commands([
            BotCommand("start", "Start Cerebro"),
            BotCommand("topics", "Review due sections"),
            BotCommand("help", "How reviews work"),
        ])

    def _authorized(self, update: Update) -> bool:
        user = update.effective_user
        if not user:
            return False
        allowed = self.config.allowed_user_id_list
        return not allowed or user.id in allowed

    async def _morning_task(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        due = await asyncio.to_thread(self.review_service.get_due_reviews_for_today)
        if not due:
            return
        users = await asyncio.to_thread(self.review_service.note_repo.fetch_telegram_users)
        allowed = self.config.allowed_user_id_list
        if allowed:
            users = [row for row in users if row["telegram_user_id"] in allowed]
        for user in users:
            try:
                await context.bot.send_message(chat_id=user["chat_id"], text=f"You have {len(due)} section(s) due. Use /topics to review.")
            except Exception:
                logger.exception("Failed to deliver daily reminder to %s", user["telegram_user_id"])

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            await update.effective_message.reply_text("This bot is not enabled for your account.")
            return
        user = update.effective_user
        await asyncio.to_thread(
            self.review_service.note_repo.register_telegram_user,
            user.id, update.effective_chat.id, user.username, user.first_name,
        )
        await update.effective_message.reply_text("Welcome to Cerebro. Use /topics to review sections due today.")
        await self.topics(update, context)

    async def topics(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            await update.effective_message.reply_text("This bot is not enabled for your account.")
            return
        due = await asyncio.to_thread(self.review_service.get_due_reviews_for_today)
        if not due:
            await update.effective_message.reply_text("Nothing is due today. Nice work.")
            return
        keyboard = [[InlineKeyboardButton(
            f"{row['note_title']} · {row['heading']}", callback_data=f"topic_{row['section_id']}"
        )] for row in due]
        await update.effective_message.reply_text("Choose a due section:", reply_markup=InlineKeyboardMarkup(keyboard))

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.effective_message.reply_text("MCQ/MSQ use buttons. Short answers accept text or voice. Every answer is evaluated and saved; weak sections return tomorrow.")

    async def handle_topic(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        if not self._authorized(update):
            await query.edit_message_text("This bot is not enabled for your account.")
            return
        section_id = int(query.data.removeprefix("topic_"))
        await query.edit_message_text("Preparing targeted questions from your notes…")
        try:
            created = await asyncio.to_thread(self.review_service.start_section_review, update.effective_user.id, section_id)
        except Exception as exc:
            logger.exception("Could not create review session for section %s", section_id)
            await query.edit_message_text(f"Could not prepare this review: {exc}")
            return
        self.sessions[update.effective_user.id] = {
            **created, "index": 0, "answers": [], "selected": set(), "waiting_for": None,
        }
        await self._render(query, update.effective_user.id, edit=True)

    async def _render(self, target: Any, user_id: int, edit: bool = False) -> None:
        session = self.sessions[user_id]
        idx = session["index"]
        if idx >= len(session["questions"]):
            await self._finish(target, user_id, edit)
            return
        q = session["questions"][idx]
        body = f"{session['section']['note_title']} · {session['section']['heading']}\nQuestion {idx + 1}/{len(session['questions'])}\n\n{q['question']}"
        keyboard: list[list[InlineKeyboardButton]] = []
        if q["type"] in ("mcq", "msq"):
            selected = session["selected"]
            for n, option in enumerate(q["options"]):
                marker = "☑" if n in selected else "□"
                keyboard.append([InlineKeyboardButton(f"{marker} {option}", callback_data=f"pick_{n}")])
            keyboard.append([InlineKeyboardButton("Submit", callback_data="submit")])
        else:
            keyboard.extend([[
                InlineKeyboardButton("Answer by text", callback_data="mode_text"),
                InlineKeyboardButton("Answer by voice", callback_data="mode_voice"),
            ]])
        markup = InlineKeyboardMarkup(keyboard)
        if edit and hasattr(target, "edit_message_text"):
            await target.edit_message_text(body, reply_markup=markup)
        else:
            message = target.message if hasattr(target, "message") else target
            await message.reply_text(body, reply_markup=markup)

    async def handle_pick(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        session = self.sessions.get(update.effective_user.id)
        if not session:
            await query.edit_message_text("Session expired. Use /topics.")
            return
        idx = int(query.data.removeprefix("pick_"))
        q = session["questions"][session["index"]]
        if idx < 0 or idx >= len(q["options"]):
            return
        if q["type"] == "mcq":
            session["selected"] = {idx}
        else:
            selected = session["selected"]
            selected.symmetric_difference_update({idx})
        await self._render(query, update.effective_user.id, edit=True)

    async def handle_submit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        session = self.sessions.get(update.effective_user.id)
        if not session:
            await query.answer("Session expired. Use /topics.")
            return
        q = session["questions"][session["index"]]
        selected = session["selected"]
        if not selected:
            await query.answer("Select at least one option first.", show_alert=True)
            return
        selected_text = [q["options"][i] for i in sorted(selected)]
        expected = q["answer"] if isinstance(q["answer"], list) else [q["answer"]]
        correct = set(selected_text) == set(expected)
        result = {"satisfied": correct, "score": 5 if correct else 1,
                  "feedback": "Correct." if correct else f"Reference answer: {', '.join(expected)}"}
        user_answer = ", ".join(selected_text)
        await self._accept_answer(query, session, q, user_answer, result)

    async def handle_answer_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        session = self.sessions.get(update.effective_user.id)
        if not session:
            await query.edit_message_text("Session expired. Use /topics.")
            return
        session["waiting_for"] = query.data.removeprefix("mode_")
        await query.edit_message_text("Send your short answer as a text message." if session["waiting_for"] == "text" else "Record and send your voice answer.")

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        session = self.sessions.get(update.effective_user.id)
        if not session or session.get("waiting_for") != "text":
            return
        q = session["questions"][session["index"]]
        text = update.effective_message.text or ""
        await update.effective_message.reply_text("Evaluating your answer…")
        try:
            result = await asyncio.to_thread(self.review_service.evaluate_text_answer, q["question"], str(q["answer"]), text)
        except Exception as exc:
            logger.exception("Text answer evaluation failed")
            await update.effective_message.reply_text(f"Evaluation failed; please try again. {exc}")
            return
        await self._accept_answer(update.effective_message, session, q, text, result)

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        session = self.sessions.get(update.effective_user.id)
        if not session or session.get("waiting_for") != "voice":
            return
        q = session["questions"][session["index"]]
        media = update.effective_message.voice or update.effective_message.audio
        await update.effective_message.reply_text("Evaluating your voice answer…")
        try:
            tg_file = await context.bot.get_file(media.file_id)
            audio = bytes(await tg_file.download_as_bytearray())
            mime_type = "audio/ogg" if update.effective_message.voice else (media.mime_type or "audio/ogg")
            result = await asyncio.to_thread(self.review_service.evaluate_audio_answer, q["question"], str(q["answer"]), audio, mime_type)
        except Exception as exc:
            logger.exception("Voice answer evaluation failed")
            await update.effective_message.reply_text(f"Voice evaluation failed; please try again. {exc}")
            return
        await self._accept_answer(update.effective_message, session, q, "[voice response]", result)

    async def _accept_answer(self, target: Any, session: dict, question: dict, user_answer: str, result: dict) -> None:
        try:
            answer = await asyncio.to_thread(self.review_service.record_answer, session["session_id"], question, user_answer, result)
        except Exception as exc:
            logger.exception("Could not persist review answer")
            await target.reply_text(f"Could not save your answer; please retry. {exc}")
            return
        session["answers"].append(answer)
        session["waiting_for"] = None
        session["selected"] = set()
        message = target.message if hasattr(target, "message") else target
        await message.reply_text(("✅ Satisfied" if result["satisfied"] else "↩ Review tomorrow") + f"\n{result.get('feedback', '')}\n\nPress Next when ready.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Next", callback_data="next")]]))

    async def handle_next(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        user_id = update.effective_user.id
        session = self.sessions.get(user_id)
        if not session:
            await query.edit_message_text("Session expired. Use /topics.")
            return
        session["index"] += 1
        await self._render(query, user_id, edit=True)

    async def _finish(self, target: Any, user_id: int, edit: bool) -> None:
        session = self.sessions[user_id]
        try:
            result = await asyncio.to_thread(
                self.review_service.finish_section_review, session["session_id"],
                session["section"]["section_id"], session["section"]["heading"], session["answers"],
            )
        except Exception as exc:
            logger.exception("Could not finish review session")
            message = f"Session answers are saved, but final scheduling failed: {exc}"
        else:
            schedule = "advanced to the next interval" if result["satisfied"] else "scheduled for tomorrow"
            message = f"Review complete · {schedule}\n\n{result['overview']}"
        self.sessions.pop(user_id, None)
        if edit and hasattr(target, "edit_message_text"):
            await target.edit_message_text(message)
        else:
            msg = target.message if hasattr(target, "message") else target
            await msg.reply_text(message)

    def run(self) -> None:
        logger.info("Telegram bot polling started")
        self.app.run_polling(drop_pending_updates=True)


def main() -> None:
    TelegramClient().run()


if __name__ == "__main__":
    main()


"""ReviewService — Manages spaced repetition quizzes, LLM question generation, and score logging."""
from __future__ import annotations

from typing import List, Dict, Any

from app.repository.note_repository import NoteRepository
from app.logging_config import setup_logging
from app.config import AppSettings
from app.client.llm.ollama_chat import OllamaChatClient
from app.clock import today

logger = setup_logging()

class ReviewService:
    def __init__(self, note_repo: NoteRepository, llm_chat_client: Any | None = None):
        self.note_repo = note_repo
        settings = AppSettings().llm
        if llm_chat_client is not None:
            self.llm_chat_client = llm_chat_client
        elif settings.gemini_api_key and settings.llm_provider.lower() == "gemini":
            from app.client.llm.gemini_client import GeminiAIClient
            self.llm_chat_client = GeminiAIClient()
        else:
            self.llm_chat_client = OllamaChatClient()

    def get_due_reviews_for_today(self) -> List[Dict[str, Any]]:
        """Fetch all subtopics due for review today directly from NoteRepository."""
        logger.info("Fetching today's scheduled subtopic reviews...")
        return self.note_repo.fetch_sections_to_review_for_specific_date(today())

    def submit_review_result(
        self,
        section_id: int,
        score: int,
        user_answer: str | None = None,
        llm_feedback: str | None = None,
        satisfied: bool | None = None,
    ) -> None:
        """
        Logs review history and advances subtopic mastery stage to its next schedule.
        """
        logger.info(f"Submitting review result for section_id {section_id} (Score: {score})")
        self.note_repo.update_section_after_review(
            section_id=section_id,
            score=score,
            user_answer=user_answer,
            llm_feedback=llm_feedback,
            satisfied=satisfied,
        )

    def start_section_review(self, telegram_user_id: int, section_id: int) -> dict:
        section = self.note_repo.fetch_section(section_id)
        if section is None:
            raise ValueError(f"Section {section_id} not found")
        history = self.note_repo.fetch_review_context(section_id)
        weak_history = [row for row in history if row.get("score") is not None and row["score"] < 4]
        feedback_context = "\n".join(
            str(row.get("llm_feedback") or "") for row in weak_history if row.get("llm_feedback")
        )
        prompt = (f"Topic: {section['note_title']} / {section['heading']}\n\n"
                  f"Learning material:\n{section.get('content') or ''}\n\n"
                  f"Prior weak areas to target in new questions:\n{feedback_context or 'None'}")
        generated = self.llm_chat_client.generate_question(prompt)
        missing_types = [name for name, values in (("MCQ", generated.mcq), ("MSQ", generated.msq), ("SAQ", generated.seq)) if not values]
        if missing_types:
            raise RuntimeError("The LLM omitted required question type(s): " + ", ".join(missing_types))
        questions = [q.model_dump() for q in generated.questions]
        questions = self.note_repo.replace_questions(section_id, questions)
        session_id = self.note_repo.create_session(telegram_user_id, section_id)
        return {"session_id": session_id, "section": section, "questions": questions}

    def evaluate_text_answer(self, question: str, reference_answer: str, user_answer: str) -> dict:
        return self.llm_chat_client.evaluate_answer(question, reference_answer, user_answer).model_dump()

    def evaluate_audio_answer(self, question: str, reference_answer: str, audio: bytes, mime_type: str = "audio/ogg") -> dict:
        method = getattr(self.llm_chat_client, "evaluate_audio_answer", None)
        if method is None and AppSettings().llm.gemini_api_key:
            from app.client.llm.gemini_client import GeminiAIClient
            method = GeminiAIClient().evaluate_audio_answer
        if method is None:
            raise RuntimeError("Voice evaluation requires GEMINI_API_KEY for Gemini multimodal audio input")
        return method(question, reference_answer, audio, mime_type).model_dump()

    def record_answer(self, session_id: int, question: dict, user_answer: str, result: dict) -> dict:
        stored_answer = result.get("transcription") or user_answer
        answer = {
            "question_id": question.get("question_id"), "question": question["question"],
            "user_answer": stored_answer, "reference_answer": self._reference(question),
            "satisfied": bool(result["satisfied"]), "feedback": result.get("feedback", ""),
        }
        self.note_repo.add_session_answer(session_id, answer)
        return answer

    @staticmethod
    def _reference(question: dict) -> str:
        answer = question.get("answer", "")
        return "; ".join(answer) if isinstance(answer, list) else str(answer)

    def finish_section_review(self, session_id: int, section_id: int, section_title: str, answers: list[dict]) -> dict:
        if not answers:
            raise ValueError("A review session must contain at least one answer")
        score = round(5 * sum(bool(a["satisfied"]) for a in answers) / len(answers))
        satisfied = all(bool(a["satisfied"]) for a in answers)
        if not satisfied:
            score = min(score, 2)
        try:
            overview = self.llm_chat_client.summarize_session(section_title, answers)
        except Exception:
            logger.exception("LLM session overview failed; using persisted evaluation feedback")
            weak = [a.get("feedback", "") for a in answers if not a.get("satisfied")]
            overview = ("Strengths: completed the review session. Weak areas: " +
                        ("; ".join(weak) if weak else "none identified") +
                        ". Revisit weak answers and key concepts in the source section.")
        self.note_repo.complete_review_session(
            session_id, section_id, satisfied=satisfied, score=score, overview=overview,
            user_answer="\n".join(a.get("user_answer", "") for a in answers),
        )
        return {"satisfied": satisfied, "score": score, "overview": overview}

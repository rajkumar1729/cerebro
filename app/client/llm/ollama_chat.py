"""OllamaChatClient — local LLM chat client for question generation and answer validation.

Mirroring GeminiAIClient interface for local Ollama models.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen
from pydantic import BaseModel

from app.logging_config import get_logger
from app.config import AppSettings, llm_config
from app.model.question import MCQ, MSQ, SEQ, QuestionList

settings = AppSettings()

logger = get_logger(__name__)

GENERATE_QUESTION_PROMPT = """
You are an expert Spaced Repetition (SR) educator and evaluation specialist.

Your task is to generate active-recall evaluation questions based on the provided learning content.

Guidelines for Question Generation:
1. **Focus on Conceptual Understanding**: Avoid superficial memorization or verbatim recall. Formulate questions that probe "why", "how", underlying mechanisms, and core trade-offs.
2. **Promote Deep Mastery**: Challenge the learner to explain key concepts, compare alternatives, analyze edge cases, or apply principles to practical scenarios.
3. **Clear & Concise**: Keep each question focused on a single mental model or core concept so it can be cleanly answered and evaluated in spaced repetition reviews.
4. **Self-Contained**: Ensure questions are clear and context-complete without needing external references outside the material.

Output Format:
Return a JSON object adhering strictly to this schema, with at least one useful question of each type:
{
  "mcq": [{"type": "mcq", "question": "...", "options": ["...", "...", "...", "..."], "answer": "...", "explanation": "..."}],
  "msq": [{"type": "msq", "question": "...", "options": ["...", "...", "...", "..."], "answer": ["..."], "explanation": "..."}],
  "seq": [{"type": "seq", "question": "...", "answer": "...", "explanation": "..."}]
}
"""

class ValidateAnswerResponse(BaseModel):
    correct: bool
    reasoning: str


class AnswerEvaluation(BaseModel):
    satisfied: bool
    score: int
    strengths: list[str] = []
    weaknesses: list[str] = []
    feedback: str
    transcription: str | None = None


class OllamaChatClient:
    """Chat with a locally-running Ollama model for active-recall question generation and validation."""

    def __init__(
        self,
        config: llm_config | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        if config is not None:
            self.model = model or config.ollama_chat_model
            self.base_url = (base_url or config.ollama_base_url).rstrip("/")
        elif settings is not None:
            self.model = model or settings.llm.ollama_chat_model
            self.base_url = (base_url or settings.llm.ollama_base_url).rstrip("/")
        else:
            self.model = model or "gemma4"
            self.base_url = (base_url or "http://localhost:11434").rstrip("/")

        self._chat_url = f"{self.base_url}/api/chat"

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        format: str | None = None,
    ) -> str:
        """Send chat messages and return assistant content."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if format is not None:
            payload["format"] = format

        req = Request(
            self._chat_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(req, timeout=180) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except URLError as err:
            raise ConnectionError(
                f"Cannot reach Ollama at {self.base_url}. "
                "Confirm Ollama is running and the model is available."
            ) from err

        if "error" in body:
            raise RuntimeError(f"Ollama chat error: {body['error']}")

        content = body.get("message", {}).get("content")
        if not isinstance(content, str):
            raise RuntimeError(f"Unexpected Ollama chat response: {json.dumps(body)[:300]}")

        return content.strip()

    def generate_question(self, contents: str) -> QuestionList:
        """Generate MCQ, MSQ, and SEQ questions using local Ollama LLM.

        Args:
            contents (str): Material/text to generate questions from.

        Returns:
            QuestionList: Pydantic container with generated MCQ, MSQ, and SEQ questions.
        """
        messages = [
            {"role": "system", "content": GENERATE_QUESTION_PROMPT},
            {"role": "user", "content": contents},
        ]
        response_text = self.chat(messages, format="json")
        clean_json = self._strip_json_fences(response_text)
        return QuestionList.model_validate_json(clean_json)

    def evaluate_answer(self, question: str, reference_answer: str, user_answer: str) -> AnswerEvaluation:
        prompt = f"""Evaluate the learner's answer for conceptual correctness, completeness, and relevance.
Accept valid paraphrases. A response is satisfied only when it demonstrates the essential ideas in the reference.
Return JSON with satisfied (boolean), score (1-5), strengths (array), weaknesses (array), and feedback (string).

Question: {question}
Reference answer: {reference_answer}
Learner answer: {user_answer}"""
        response = self.chat([{"role": "user", "content": prompt}], format="json")
        result = AnswerEvaluation.model_validate_json(self._strip_json_fences(response))
        result.score = max(1, min(5, result.score))
        return result

    def summarize_session(self, topic: str, answers: list[dict]) -> str:
        prompt = ("Summarize this active-recall session. State strengths, weak concepts, and one actionable "
                  "practice suggestion. Be concise and base conclusions only on this data.\n"
                  f"Topic: {topic}\nSession data: {json.dumps(answers, ensure_ascii=False)}")
        return self.chat([{"role": "user", "content": prompt}], temperature=0.3)

    def validate_answer_with_audio(
        self, question: str, audio: bytes, reference_answer: str | None = None
    ) -> ValidateAnswerResponse:
        """Validate user spoken or text answer against target answer.

        Args:
            question (str): Question prompt asked.
            audio (bytes): Audio file or text transcription bytes.

        Returns:
            ValidateAnswerResponse: Validation result with correctness flag and reasoning.
        """
        raise RuntimeError("Ollama text chat cannot evaluate raw audio. Use Gemini multimodal audio input.")

    @staticmethod
    def _strip_json_fences(text: str) -> str:
        """Helper to remove ```json ... ``` markdown codeblock wrappers if present."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        return cleaned

    def is_available(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            req = Request(f"{self.base_url}/api/tags", method="GET")
            with urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except (URLError, OSError):
            return False

if __name__ == "__main__":
    client = OllamaChatClient()
    example_contents = """
    Quantum theory is the foundational branch of physics that explains the nature and behavior of matter and energy at the microscopic, subatomic level...
    """

    # 1. Generate questions (returns a QuestionList)
    question_list = client.generate_question(example_contents)

    # 2. Iterate through the generated questions properly
    for q in question_list.questions:
        print(f"Generated Question: {q}")

        # Example of how you would validate an answer if you had audio bytes:
        # dummy_audio_bytes = b"..."
        # result = client.validate_answer_with_audio(question=q.question_text, audio=dummy_audio_bytes)
        # print(f"Correct: {result.correct}, Reasoning: {result.reasoning}")

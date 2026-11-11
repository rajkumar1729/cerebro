from google import genai
from google.genai import types
from pydantic import BaseModel

from app.config import AppSettings

settings = AppSettings()

GENERATE_QUESTION_PROMPT = """
You are an expert Spaced Repetition (SR) educator and evaluation specialist.

Your task is to generate active-recall evaluation questions based on the provided learning content.

Guidelines for Question Generation:
1. **Focus on Conceptual Understanding**: Avoid superficial memorization or verbatim recall. Formulate questions that probe "why", "how", underlying mechanisms, and core trade-offs.
2. **Promote Deep Mastery**: Challenge the learner to explain key concepts, compare alternatives, analyze edge cases, or apply principles to practical scenarios.
3. **Clear & Concise**: Keep each question focused on a single mental model or core concept so it can be cleanly answered and evaluated in spaced repetition reviews.
4. **Self-Contained**: Ensure questions are clear and context-complete without needing external references outside the material.

Return strict JSON with this schema:
{"mcq":[{"type":"mcq","question":"...","options":["..."],"answer":"...","explanation":"..."}],
 "msq":[{"type":"msq","question":"...","options":["..."],"answer":["..."],"explanation":"..."}],
 "seq":[{"type":"seq","question":"...","answer":"...","explanation":"..."}]}
Include at least one question of each type.
"""

ANSWER_VALIDATOR_PROMPT = """
You are an expert in Speech Recognition and Natural Language Processing. Your task is to determine if a user's spoken answer correctly answers the given question.

## INSTRUCTIONS

1. **STRICT VERBATIM MATCH REQUIRED**: You must compare the transcribed text from the audio directly against the target answer.
2. **NO FACILITATION**: Do NOT accept synonyms, rephrased explanations, or semantically similar statements. The user must use the exact same key terms and phrasing as the target answer.
3. **STRICT SPELLING VERIFICATION**: If the target answer contains a specific technical term, variable name, or proper noun, the user's transcription must match that spelling exactly.
4. **Strictly analyze the following two inputs**:
   - **Question**: {question}
   - **Spoken Answer (transcribed text)**: {answer_transcription}
5. **Return only a JSON object with the following structure**:
6. If you are unsure, default to **false**.
"""


from app.model.question import MCQ, MSQ, SEQ, QuestionList
from app.client.llm.ollama_chat import AnswerEvaluation


class ValidateAnswerResponse(BaseModel):
    correct: bool
    reasoning: str


class GeminiAIClient:
    def __init__(self):
        self.client = genai.Client(api_key=settings.llm.gemini_api_key)
        self.model = settings.llm.gemini_chat_model

    def generate_question(self, contents: str) -> QuestionList:
        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=GENERATE_QUESTION_PROMPT,
                response_mime_type="application/json",
                response_schema=QuestionList,
            ),
        )
        if isinstance(response.parsed, QuestionList):
            return response.parsed
        return QuestionList.model_validate_json(response.text)

    def evaluate_answer(self, question: str, reference_answer: str, user_answer: str) -> AnswerEvaluation:
        prompt = ("Evaluate conceptual correctness, completeness, and relevance. Accept valid paraphrases. "
                  "Return whether satisfied, score 1-5, strengths, weaknesses, and concise feedback.\n"
                  f"Question: {question}\nReference answer: {reference_answer}\nLearner answer: {user_answer}")
        response = self.client.models.generate_content(
            model=self.model, contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=AnswerEvaluation),
        )
        result = response.parsed if isinstance(response.parsed, AnswerEvaluation) else AnswerEvaluation.model_validate_json(response.text)
        result.score = max(1, min(5, result.score))
        return result

    def evaluate_audio_answer(self, question: str, reference_answer: str, audio: bytes, mime_type: str = "audio/ogg") -> AnswerEvaluation:
        prompt = ("Listen to the learner's spoken answer, transcribe it, and evaluate conceptual correctness, completeness, and relevance. "
                  "Accept valid paraphrases; do not require verbatim wording. Return satisfied, score 1-5, strengths, "
                  "weaknesses, concise feedback, and the transcription as JSON.\n"
                  f"Question: {question}\nReference answer: {reference_answer}")
        audio_part = types.Part.from_bytes(data=audio, mime_type=mime_type)
        response = self.client.models.generate_content(
            model=self.model, contents=[prompt, audio_part],
            config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=AnswerEvaluation),
        )
        result = response.parsed if isinstance(response.parsed, AnswerEvaluation) else AnswerEvaluation.model_validate_json(response.text)
        result.score = max(1, min(5, result.score))
        return result

    def summarize_session(self, topic: str, answers: list[dict]) -> str:
        response = self.client.models.generate_content(
            model=self.model,
            contents=f"Summarize strengths, weak concepts, and an actionable practice suggestion. Be concise.\nTopic: {topic}\nData: {answers}",
        )
        return response.text or "Session complete. Review the topics with lower scores tomorrow."

    def validate_answer_with_audio(self, question: str, audio: bytes, reference_answer: str) -> ValidateAnswerResponse:
        result = self.evaluate_audio_answer(question, reference_answer, audio)
        return ValidateAnswerResponse(correct=result.satisfied, reasoning=result.feedback)


if __name__ == "__main__":
    client = GeminiAIClient()
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

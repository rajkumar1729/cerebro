"""Pydantic models for MCQ, MSQ, and SEQ review questions."""
from __future__ import annotations

from typing import List, Union, Literal, Annotated
from pydantic import BaseModel, Field, model_validator


class MCQ(BaseModel):
    """Multiple Choice Question (Single Select)."""
    type: Literal["mcq"] = "mcq"
    question: str = Field(..., description="Question prompt text")
    options: List[str] = Field(..., description="List of options (e.g. 4 options)")
    answer: str = Field(..., description="Correct single option text")
    explanation: str = Field(..., description="Explanation of the correct answer")

    @model_validator(mode="after")
    def validate_key(self) -> "MCQ":
        if len(self.options) < 2 or self.answer not in self.options:
            raise ValueError("MCQ needs at least two options and its answer must be one of them")
        return self


class MSQ(BaseModel):
    """Multiple Select Question (Multi-select)."""
    type: Literal["msq"] = "msq"
    question: str = Field(..., description="Question prompt text")
    options: List[str] = Field(..., description="List of selectable options")
    answer: List[str] = Field(..., description="List of correct option texts")
    explanation: str = Field(..., description="Explanation of the correct answers")

    @model_validator(mode="after")
    def validate_key(self) -> "MSQ":
        if len(self.options) < 2 or not self.answer or not set(self.answer).issubset(self.options):
            raise ValueError("MSQ needs at least two options and all correct answers must be options")
        return self


class SEQ(BaseModel):
    """Short Answer / Subjective Essay Question."""
    type: Literal["seq"] = "seq"
    question: str = Field(..., description="Question prompt text")
    answer: str = Field(..., description="Expected correct answer / key concepts")
    explanation: str = Field(..., description="Detailed explanation or scoring guide")


# Discriminated union based on 'type' field for automated deserialization
QuestionType = Annotated[Union[MCQ, MSQ, SEQ], Field(discriminator="type")]


class QuestionList(BaseModel):
    """Container schema for generated questions."""
    mcq: List[MCQ] = Field(default_factory=list)
    msq: List[MSQ] = Field(default_factory=list)
    seq: List[SEQ] = Field(default_factory=list)

    @property
    def questions(self) -> List[QuestionType]:
        """Flattened list of all generated questions."""
        return [*self.mcq, *self.msq, *self.seq]


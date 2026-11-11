from typing import Literal, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator
from enum import Enum
from datetime import datetime, date

class MasteryStage(str, Enum):
    NOVICE = "novice"             # Day 1
    APPRENTICE = "apprentice"     # Day 3
    PRACTITIONER = "practitioner" # Day 7
    ADEPT = "adept"               # Day 14
    SCHOLAR = "scholar"           # Day 30
    EXPERT = "expert"             # Day 60
    MASTER = "master"             # Day 120

    @property
    def interval_days(self) -> int:
        intervals = {
            MasteryStage.NOVICE: 1,
            MasteryStage.APPRENTICE: 3,
            MasteryStage.PRACTITIONER: 7,
            MasteryStage.ADEPT: 14,
            MasteryStage.SCHOLAR: 30,
            MasteryStage.EXPERT: 60,
            MasteryStage.MASTER: 120,
        }
        return intervals[self]

    @property
    def next_stage(self) -> "MasteryStage":
        progression = {
            MasteryStage.NOVICE: MasteryStage.APPRENTICE,
            MasteryStage.APPRENTICE: MasteryStage.PRACTITIONER,
            MasteryStage.PRACTITIONER: MasteryStage.ADEPT,
            MasteryStage.ADEPT: MasteryStage.SCHOLAR,
            MasteryStage.SCHOLAR: MasteryStage.EXPERT,
            MasteryStage.EXPERT: MasteryStage.MASTER,
            MasteryStage.MASTER: MasteryStage.MASTER,
        }
        return progression[self]

    @property
    def stage_weight(self) -> float:
        weights = {
            MasteryStage.NOVICE: 0.1,
            MasteryStage.APPRENTICE: 0.25,
            MasteryStage.PRACTITIONER: 0.4,
            MasteryStage.ADEPT: 0.6,
            MasteryStage.SCHOLAR: 0.75,
            MasteryStage.EXPERT: 0.9,
            MasteryStage.MASTER: 1.0,
        }
        return weights[self]

STATUS = Literal["active", "archived", "deleted"]

class Note(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int | None = Field(None, alias="note_id", description="The unique identifier for the note.")
    file_path: str = Field(..., description="The file path associated with the note.")
    title: str = Field(default="Untitled", description="The title of the note.")
    topic: str = Field(default="General", description="The topic or category of the note.")
    tags: list[str] = Field(default_factory=list, description="A list of tags associated with the note.")
    created_at: str | datetime = Field(..., description="The timestamp when the note was created.")
    updated_at: str | datetime = Field(..., description="The timestamp when the note was last updated.")
    status: STATUS = Field(default="active", description="The status of the note (e.g., active, archived).")

    @field_validator("title", mode="before")
    @classmethod
    def coerce_title(cls, v: Any) -> str:
        if v is None or not str(v).strip():
            return "Untitled"
        return str(v).strip()

    @field_validator("topic", mode="before")
    @classmethod
    def coerce_topic(cls, v: Any) -> str:
        if v is None or not str(v).strip():
            return "General"
        return str(v).strip()

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        if isinstance(v, (list, tuple, set)):
            return [str(t).strip() for t in v if t is not None and str(t).strip()]
        return []

class NoteSection(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    section_id: int | None = Field(None, description="The unique identifier for the note section.")
    note_id: int = Field(..., description="The identifier of the note associated with this section.")
    heading: str = Field(..., description="The heading title of the subtopic section.")
    content: str | None = Field(None, description="The content of the subtopic section.")
    review_stage: MasteryStage = Field(default=MasteryStage.NOVICE, description="The current review stage of the section.")
    mastery_score: float = Field(default=MasteryStage.NOVICE.stage_weight, description="The mastery score of the section.")
    next_review_date: str | date = Field(..., description="The date when the section is next scheduled for review.")
    last_reviewed_at: str | datetime | None = Field(None, description="The timestamp when the section was last reviewed.")
    review_count: int = Field(default=0, description="The number of times the section has been reviewed.")
    embedding: list[float] = Field(default_factory=list, description="The embedding vector of the section.")
    embedding_model: str | None = None
    created_at: str | datetime | None = Field(None, description="The timestamp when the section was created.")
    updated_at: str | datetime | None = Field(None, description="The timestamp when the section was last updated.")

class ReviewHistory(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    review_id: int | None = Field(None, description="The unique identifier for the review history entry.")
    note_id: int = Field(..., description="The identifier of the note associated with this review history entry.")
    section_id: int | None = Field(None, description="The identifier of the specific note section reviewed.")
    review_date: str | datetime = Field(..., description="The timestamp when the review took place.")
    score: int | None = Field(None, description="The score given during the review.")
    user_answer: str | None = Field(None, description="The answer provided by the user during the review.")
    llm_feedback: str | None = Field(None, description="Feedback provided by the language model during the review.")

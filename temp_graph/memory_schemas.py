from pydantic import BaseModel, Field


class LearnedLesson(BaseModel):
    """A durable lesson distilled from an answer the user accepted as correct/useful."""

    question: str = Field(description="A concise rephrasing of what the user asked")
    lesson: str = Field(
        description="The concise, self-contained fact or answer worth remembering "
        "for future differently-worded questions on this topic"
    )
    reason: str = Field(description="Why this is worth remembering")


class FailureLesson(BaseModel):
    """A durable lesson distilled from an answer the user rejected as wrong/unhelpful."""

    question: str = Field(description="A concise rephrasing of what the user asked")
    mistake: str = Field(description="What the rejected answer got wrong or missed")
    guidance: str = Field(
        description="What to do differently when a similar question comes up again"
    )
    reason: str = Field(description="Why this failure is worth remembering")

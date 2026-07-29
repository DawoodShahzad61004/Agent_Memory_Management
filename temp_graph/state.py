from typing import NotRequired, TypedDict


class GraphState(TypedDict):
    user_input: str
    answer: NotRequired[str]

"""Errors of the evaluation harness."""

from __future__ import annotations

from aireviewer.errors import AIReviewerError


class EvalInputError(AIReviewerError):
    """An evaluation input (cases, predictions, adjudications) is invalid.

    `messages` are complete, human-readable lines naming the file and the field.
    """

    def __init__(self, *messages: str) -> None:
        super().__init__("\n".join(messages))
        self.messages = messages

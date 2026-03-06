"""
Typed exception hierarchy for the Databar SDK.

All exceptions carry:
  - message: human-readable description
  - status_code: HTTP status (where applicable)
  - response_body: raw response dict (where applicable)
"""

from __future__ import annotations

from typing import Any, Optional


class DatabarError(Exception):
    """Base exception for all Databar SDK errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_body = response_body

    def __repr__(self) -> str:
        parts = [f"message={self.message!r}"]
        if self.status_code is not None:
            parts.append(f"status_code={self.status_code}")
        return f"{self.__class__.__name__}({', '.join(parts)})"


class DatabarAuthError(DatabarError):
    """Raised on 401 or 403 — invalid or missing API key."""


class DatabarNotFoundError(DatabarError):
    """Raised on 404 — enrichment, waterfall, table, or task not found."""


class DatabarInsufficientCreditsError(DatabarError):
    """Raised on 406 — account does not have enough credits."""


class DatabarGoneError(DatabarError):
    """Raised on 410 — task results have expired (data only stored 1 hour)."""


class DatabarValidationError(DatabarError):
    """Raised on 422 — request body failed schema validation."""

    def __init__(
        self,
        message: str,
        errors: Optional[list] = None,
        status_code: int = 422,
        response_body: Any = None,
    ) -> None:
        super().__init__(message, status_code=status_code, response_body=response_body)
        self.errors = errors or []


class DatabarRateLimitError(DatabarError):
    """Raised on 429 — rate limit exceeded."""


class DatabarTaskFailedError(DatabarError):
    """Raised when a polled task returns status 'failed'."""

    def __init__(
        self,
        message: str,
        task_id: str | None = None,
        response_body: Any = None,
    ) -> None:
        super().__init__(message, response_body=response_body)
        self.task_id = task_id


class DatabarTimeoutError(DatabarError):
    """Raised when polling a task exceeds max_poll_attempts without completing."""

    def __init__(self, task_id: str, max_attempts: int, interval_s: float) -> None:
        elapsed = max_attempts * interval_s
        super().__init__(
            f"Task {task_id!r} did not complete after {max_attempts} polls "
            f"({elapsed:.0f}s). The task may still be running — use "
            f"client.get_task({task_id!r}) to check its status."
        )
        self.task_id = task_id
        self.max_attempts = max_attempts
        self.interval_s = interval_s

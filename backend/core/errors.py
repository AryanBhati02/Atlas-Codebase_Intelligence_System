"""Custom exception hierarchy for Atlas.

Handlers catch AtlasError subclasses and return structured JSON with
{ "error": message, "code": code } and the appropriate HTTP status code.
Never return a Python traceback to the client.
"""

from typing import Optional


class AtlasError(Exception):
    """Base class for all Atlas application errors."""

    def __init__(
        self,
        message: str,
        code: str,
        status_code: int = 500,
        detail: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.detail = detail

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"error": self.message, "code": self.code}
        if self.detail:
            payload["detail"] = self.detail
        return payload


class RepoTooLargeError(AtlasError):
    """Repository exceeds the configured file-count or size limit."""

    def __init__(self, message: str = "Repository exceeds size limit") -> None:
        super().__init__(message, code="REPO_TOO_LARGE", status_code=413)


class CloneFailedError(AtlasError):
    """git clone subprocess exited non-zero or the URL was invalid."""

    def __init__(self, message: str = "Failed to clone repository") -> None:
        super().__init__(message, code="CLONE_FAILED", status_code=422)


class ParseTimeoutError(AtlasError):
    """AST parsing exceeded the configured timeout."""

    def __init__(self, message: str = "Parsing timed out") -> None:
        super().__init__(message, code="PARSE_TIMEOUT", status_code=504)


class ProviderUnavailableError(AtlasError):
    """All AI providers in the chain are unavailable or exhausted."""

    def __init__(self, message: str = "No AI provider available") -> None:
        super().__init__(message, code="PROVIDER_UNAVAILABLE", status_code=503)


class SessionNotFoundError(AtlasError):
    """The requested session_id does not exist or has expired."""

    def __init__(self, session_id: str = "") -> None:
        msg = (
            f"Session not found: {session_id}"
            if session_id
            else "Session not found"
        )
        super().__init__(msg, code="SESSION_NOT_FOUND", status_code=404)


class InvalidRepoURLError(AtlasError):
    """The provided repository URL is not a valid GitHub URL."""

    def __init__(self, url: str = "") -> None:
        msg = f"Invalid repository URL: {url}" if url else "Invalid repository URL"
        super().__init__(msg, code="INVALID_REPO_URL", status_code=400)

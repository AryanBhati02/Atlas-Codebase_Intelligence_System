
from typing import Optional

class AtlasError(Exception):

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

    def __init__(self, message: str = "Repository exceeds size limit") -> None:
        super().__init__(message, code="REPO_TOO_LARGE", status_code=413)

class CloneFailedError(AtlasError):

    def __init__(self, message: str = "Failed to clone repository") -> None:
        super().__init__(message, code="CLONE_FAILED", status_code=422)

class ParseTimeoutError(AtlasError):

    def __init__(self, message: str = "Parsing timed out") -> None:
        super().__init__(message, code="PARSE_TIMEOUT", status_code=504)

class ProviderUnavailableError(AtlasError):

    def __init__(self, message: str = "No AI provider available") -> None:
        super().__init__(message, code="PROVIDER_UNAVAILABLE", status_code=503)

class SessionNotFoundError(AtlasError):

    def __init__(self, session_id: str = "") -> None:
        msg = (
            f"Session not found: {session_id}"
            if session_id
            else "Session not found"
        )
        super().__init__(msg, code="SESSION_NOT_FOUND", status_code=404)

class InvalidRepoURLError(AtlasError):

    def __init__(self, url: str = "") -> None:
        msg = f"Invalid repository URL: {url}" if url else "Invalid repository URL"
        super().__init__(msg, code="INVALID_REPO_URL", status_code=400)

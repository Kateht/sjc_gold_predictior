from __future__ import annotations


class AppError(Exception):
    status_code = 500
    default_detail = "Internal server error"

    def __init__(self, detail: str | None = None):
        super().__init__(detail or self.default_detail)
        self.detail = detail or self.default_detail


class BadRequestError(AppError):
    status_code = 400
    default_detail = "Bad request"


class UnauthorizedError(AppError):
    status_code = 401
    default_detail = "Unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    default_detail = "Forbidden"


class NotFoundError(AppError):
    status_code = 404
    default_detail = "Not found"


class ConflictError(AppError):
    status_code = 409
    default_detail = "Conflict"


class ExternalServiceError(AppError):
    status_code = 502
    default_detail = "External service error"


class CrawlerExecutionError(AppError):
    status_code = 500
    default_detail = "Crawler execution failed"

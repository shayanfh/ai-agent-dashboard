from fastapi import HTTPException, status


class AppException(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, details=None):
        super().__init__(status_code=status_code, detail={"code": code, "message": message, "details": details})


class NotFoundError(AppException):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(status.HTTP_404_NOT_FOUND, "RESOURCE_NOT_FOUND", message)


class PermissionDeniedError(AppException):
    def __init__(self, message: str = "Permission denied"):
        super().__init__(status.HTTP_403_FORBIDDEN, "PERMISSION_DENIED", message)


class ValidationError(AppException):
    def __init__(self, message: str, details=None):
        super().__init__(status.HTTP_422_UNPROCESSABLE_ENTITY, "VALIDATION_ERROR", message, details)


class ConflictError(AppException):
    def __init__(self, message: str):
        super().__init__(status.HTTP_409_CONFLICT, "CONFLICT", message)


class AuthenticationError(AppException):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(status.HTTP_401_UNAUTHORIZED, "AUTHENTICATION_ERROR", message)


class EmailNotVerifiedError(AppException):
    def __init__(self):
        super().__init__(
            status.HTTP_403_FORBIDDEN,
            "EMAIL_NOT_VERIFIED",
            "Please verify your email before signing in.",
        )


class RateLimitError(AppException):
    def __init__(self):
        super().__init__(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "RATE_LIMITED",
            "Too many requests. Please try again later.",
        )


class IntegrationError(AppException):
    def __init__(self, message: str, details=None):
        super().__init__(status.HTTP_502_BAD_GATEWAY, "INTEGRATION_ERROR", message, details)


class EntitlementError(AppException):
    """A subscription or plan entitlement prevents the requested operation."""

    def __init__(self, code: str, message: str, details=None, status_code: int = 403):
        super().__init__(status_code, code, message, details)

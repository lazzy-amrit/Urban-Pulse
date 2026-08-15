"""
Standard error envelope for the whole API.

All HTTPExceptions raised across the app should use `api_error()` so every
error response has the shape:

{
  "detail": {
    "code": "ERROR_CODE",
    "message": "Human readable message"
  }
}
"""

from fastapi import HTTPException


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


# Common reusable errors -----------------------------------------------------

def unauthorized(message: str = "Authentication required.") -> HTTPException:
    return api_error(401, "UNAUTHORIZED", message)


def forbidden(message: str = "You do not have access to this resource.") -> HTTPException:
    return api_error(403, "FORBIDDEN", message)


def not_found(message: str = "Resource not found.") -> HTTPException:
    return api_error(404, "NOT_FOUND", message)


def conflict(message: str = "Resource already exists.") -> HTTPException:
    return api_error(409, "CONFLICT", message)


def bad_request(message: str = "Invalid request.") -> HTTPException:
    return api_error(400, "BAD_REQUEST", message)


def validation_error(message: str = "Validation failed.") -> HTTPException:
    return api_error(422, "VALIDATION_ERROR", message)

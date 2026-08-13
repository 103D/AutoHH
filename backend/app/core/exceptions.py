"""Custom exceptions for the application."""

class JobHunterException(Exception):
    """Base exception for all application errors."""
    pass

class NotFoundError(JobHunterException):
    """Resource not found."""
    pass

class ValidationError(JobHunterException):
    """Validation error."""
    pass

class AIProviderError(JobHunterException):
    """AI provider error."""
    pass

class JobSourceError(JobHunterException):
    """Job source error."""
    pass

class DuplicateError(JobHunterException):
    """Duplicate resource."""
    pass
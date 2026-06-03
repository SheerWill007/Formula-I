"""
Custom exception classes for the application.
"""


class PitwallException(Exception):
    """Base exception for all Pitwall errors."""
    
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class ResourceNotFoundError(PitwallException):
    """Raised when a requested resource is not found."""
    
    def __init__(self, resource: str, identifier: str | int):
        message = f"{resource} with identifier '{identifier}' not found"
        super().__init__(message, status_code=404)


class DatabaseConnectionError(PitwallException):
    """Raised when database connection fails."""
    
    def __init__(self, detail: str):
        message = f"Cannot connect to database: {detail}"
        super().__init__(message, status_code=503)


class SchemaNotInitializedError(PitwallException):
    """Raised when database schema is not initialized."""
    
    def __init__(self):
        message = "Database schema is not initialized. Run migrations first."
        super().__init__(message, status_code=503)


class ValidationError(PitwallException):
    """Raised when request validation fails."""
    
    def __init__(self, field: str, reason: str):
        message = f"Validation error for field '{field}': {reason}"
        super().__init__(message, status_code=400)


class ExternalAPIError(PitwallException):
    """Raised when an external API call fails."""
    
    def __init__(self, api_name: str, detail: str):
        message = f"External API '{api_name}' failed: {detail}"
        super().__init__(message, status_code=503)

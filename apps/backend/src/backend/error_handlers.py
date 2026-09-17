"""
Centralized error handlers for Flask app.
"""
import structlog
from flask import jsonify, Flask
from sqlalchemy.exc import ProgrammingError, OperationalError
from pydantic import ValidationError as PydanticValidationError

from backend.exceptions import (
    PitwallException,
    ResourceNotFoundError,
    DatabaseConnectionError,
    SchemaNotInitializedError,
)

log = structlog.get_logger()


def _is_missing_table_error(exc: ProgrammingError) -> bool:
    """Check if exception is due to missing table."""
    return "UndefinedTable" in exc.__class__.__name__ or "does not exist" in str(exc.orig)


def register_error_handlers(app: Flask) -> None:
    """Register all error handlers with the Flask app."""

    @app.errorhandler(PitwallException)
    def handle_pitwall_exception(error: PitwallException):
        """Handle custom Pitwall exceptions."""
        log.warning(
            "pitwall_exception",
            message=error.message,
            status_code=error.status_code,
        )
        return jsonify({
            "error": error.message,
            "code": error.status_code
        }), error.status_code

    @app.errorhandler(ResourceNotFoundError)
    def handle_not_found(error: ResourceNotFoundError):
        """Handle resource not found errors."""
        return jsonify({
            "error": error.message,
            "code": 404
        }), 404

    @app.errorhandler(SchemaNotInitializedError)
    def handle_schema_not_initialized(error: SchemaNotInitializedError):
        """Handle schema not initialized errors."""
        return jsonify({
            "error": "Database schema is not initialized",
            "detail": "The backend connected to Postgres, but required tables do not exist.",
            "suggested_command": "uv run alembic -c backend/alembic.ini upgrade head",
            "code": 503
        }), 503

    @app.errorhandler(ProgrammingError)
    def handle_programming_error(error: ProgrammingError):
        """Handle SQLAlchemy programming errors (missing tables, etc.)."""
        if _is_missing_table_error(error):
            return handle_schema_not_initialized(SchemaNotInitializedError())
        
        log.exception("database_programming_error", error=str(error))
        return jsonify({
            "error": "Database query error",
            "detail": str(error.orig) if hasattr(error, 'orig') else str(error),
            "code": 500
        }), 500

    @app.errorhandler(OperationalError)
    def handle_operational_error(error: OperationalError):
        """Handle SQLAlchemy operational errors (connection issues, etc.)."""
        log.exception("database_operational_error", error=str(error))
        return jsonify({
            "error": "Cannot connect to database",
            "detail": str(error.orig) if hasattr(error, 'orig') else str(error),
            "hint": "Ensure PostgreSQL is running and DATABASE_URL is configured correctly",
            "code": 503
        }), 503

    @app.errorhandler(PydanticValidationError)
    def handle_validation_error(error: PydanticValidationError):
        """Handle Pydantic validation errors."""
        log.warning("validation_error", errors=error.errors())
        return jsonify({
            "error": "Validation error",
            "details": error.errors(),
            "code": 400
        }), 400

    @app.errorhandler(404)
    def handle_404(error):
        """Handle 404 errors."""
        return jsonify({
            "error": "Not found",
            "code": 404
        }), 404

    @app.errorhandler(500)
    def handle_500(error):
        """Handle 500 errors."""
        log.exception("unhandled_exception", error=str(error))
        return jsonify({
            "error": "Internal server error",
            "code": 500
        }), 500

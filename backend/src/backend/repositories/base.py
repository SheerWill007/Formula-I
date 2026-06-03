"""
Base repository with common CRUD operations.
"""
from typing import Generic, TypeVar, Type, Optional, List, Any
from sqlalchemy import select, delete, update
from sqlalchemy.orm import Session as DBSession

from backend.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Base repository with common database operations."""

    def __init__(self, model: Type[ModelType], db: DBSession):
        self.model = model
        self.db = db

    def get_by_id(self, id_value: Any) -> Optional[ModelType]:
        """Get a single record by primary key."""
        return self.db.get(self.model, id_value)

    def get_all(self, skip: int = 0, limit: int = 100) -> List[ModelType]:
        """Get all records with pagination."""
        stmt = select(self.model).offset(skip).limit(limit)
        result = self.db.execute(stmt)
        return list(result.scalars().all())

    def create(self, **kwargs) -> ModelType:
        """Create a new record."""
        instance = self.model(**kwargs)
        self.db.add(instance)
        self.db.flush()
        self.db.refresh(instance)
        return instance

    def update(self, id_value: Any, **kwargs) -> Optional[ModelType]:
        """Update an existing record."""
        stmt = (
            update(self.model)
            .where(self.model.id == id_value)
            .values(**kwargs)
            .returning(self.model)
        )
        result = self.db.execute(stmt)
        self.db.flush()
        return result.scalar_one_or_none()

    def delete(self, id_value: Any) -> bool:
        """Delete a record by primary key."""
        stmt = delete(self.model).where(self.model.id == id_value)
        result = self.db.execute(stmt)
        self.db.flush()
        return result.rowcount > 0

    def count(self) -> int:
        """Count total records."""
        stmt = select(self.model)
        result = self.db.execute(stmt)
        return len(list(result.scalars().all()))

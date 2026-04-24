from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Column, ForeignKey, JSON, String
from sqlalchemy.orm import relationship

from app.domain.models.base import Base, TimestampMixin


class MaterialSet(Base, TimestampMixin):
    """Project-scoped material set for character/location visuals."""

    __tablename__ = "material_sets"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    project_id = Column(String(32), ForeignKey("projects.id"), nullable=False, index=True)
    asset_type = Column(String(32), nullable=False, index=True)  # character | location
    asset_id = Column(String(32), nullable=False, index=True)  # project asset id
    label = Column(String(255), nullable=False)
    reference_images = Column(JSON, nullable=True)
    material_metadata = Column(JSON, nullable=True)

    project = relationship("Project")

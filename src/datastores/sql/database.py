# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Unicode,
    UnicodeText,
    create_engine,
    event,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Query,
    Session,
    declared_attr,
    mapped_column,
    relationship,
    sessionmaker,
)

if TYPE_CHECKING:
    pass

from config import config

SQLALCHEMY_DATABASE_URL = config["datastores"]["sqlalchemy"]["database_url"]
SQLALCHEMY_DATABASE_URL_ENV = os.getenv("SQLALCHEMY_DATABASE_URL")

if SQLALCHEMY_DATABASE_URL_ENV:
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL_ENV

# For SQLite you need to set check_same_thread
# engine = create_engine(
#    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
# )

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=True, bind=engine)


# Define base class with common fields for all models
class BaseModel(DeclarativeBase):
    """Define common columns to mapped classes using this class as a base class.

    Attributes:
        id (int): The primary key of the model.
        created_at (datetime): The timestamp when the model was created.
        updated_at (datetime): The timestamp when the model was last updated.
        deleted_at (datetime): The timestamp when the model was deleted.
        is_deleted (bool): Whether the model is deleted.
    """

    @declared_attr.directive
    # Automatically create column name from class name
    def __tablename__(cls) -> str:
        return cls.__name__.lower()

    # Common columns
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(default=False)

    purged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    is_purged: Mapped[bool] = mapped_column(default=False)

    def soft_delete(self, db: Session):
        self.deleted_at = func.now()
        self.is_deleted = True
        db.commit()


class AttributeMixin:
    """Mixin class for defining attributes.

    To use this mixin, inherit from this mixin and define the following attributes:
        model_id (int): The ID of the model the attribute is associated with.
        model (Model): The model the attribute is associated with.

    # Example using this mixin to add attributes to a File object:
    class FileAttribute(BaseModel, AttributeMixin):
        file_id: Mapped[int] = mapped_column(ForeignKey("file.id"))
        file: Mapped["File"] = relationship(back_populates="attributes")

    # And on the File class, add a relationship:
    attributes: Mapped[List["FileAttribute"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )

    Attributes:
        key (str): The key of the attribute.
        value (str): The value of the attribute.
        ontology (str): The ontology of the attribute.
        description (str): The description of the attribute.
        user_id (int): The ID of the user who created the attribute.
        user (User): The user who created the attribute.
    """

    key: Mapped[str] = mapped_column(Unicode(255), index=True)
    value: Mapped[str] = mapped_column(UnicodeText)
    ontology: Mapped[str] = mapped_column(Unicode(255), index=True)
    description: Mapped[Optional[str]] = mapped_column(UnicodeText)

    # Track who created the attribute.
    @declared_attr
    def user_id(cls):
        return mapped_column(ForeignKey("user.id"))

    @declared_attr
    def user(cls):
        return relationship("User")  # No back_populates needed


class FeedbackMixin:
    """Mixin class for defining attributes.

    To use this mixin, inherit from this mixin and define the following attributes:
        model_id (int): The ID of the model the attribute is associated with.
        model (Model): The model the attribute is associated with.

    # Example using this mixin to add attributes to a FileSummary object:
    class FileSummaryFeedback(BaseModel, FeedbackMixin):
        file_summary_id: Mapped[int] = mapped_column(ForeignKey("file_summary.id"))
        file_summary: Mapped["FileSummary"] = relationship(back_populates="feedbacks")

    # And on the FileSummary class, add a relationship:
    feedbacks: Mapped[List["FileSummaryFeedback"]] = relationship(
        back_populates="file_summary", cascade="all, delete-orphan"
    )

    Attributes:
        upvote (bool): Indicates whether the user upvoted the summary.
        downvote (bool): Indicates whether the user downvoted the summary.
        feedback_text (str): Optional text feedback from the user.
        user_id (int): The ID of the user who created the feedback
        user (User): The user who created the feedback
    """

    upvote: Mapped[bool] = mapped_column(Boolean, default=False)
    downvote: Mapped[bool] = mapped_column(Boolean, default=False)
    feedback_text: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)

    # Track who created the attribute.
    @declared_attr
    def user_id(cls):
        return mapped_column(ForeignKey("user.id"))

    @declared_attr
    def user(cls):
        return relationship("User")  # No back_populates needed


@event.listens_for(Query, "before_compile", retval=True)
def before_compile(query):
    # If the query has `_include_deleted` = True, skip adding "is_deleted == False"
    if getattr(query, "_include_deleted", False):
        return query

    for desc in query.column_descriptions:
        entity = desc["entity"]
        query = query.enable_assertions(False).filter(
            (entity.is_deleted == False) | (entity.is_deleted == None)
        )
    return query


# Database connection, used as a dependency inhjection.
def get_db_connection():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

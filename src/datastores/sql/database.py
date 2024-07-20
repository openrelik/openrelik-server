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

from sqlalchemy import (
    BigInteger,
    DateTime,
    Integer,
    Table,
    Column,
    ForeignKey,
    create_engine,
    func,
    event,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    declared_attr,
    mapped_column,
    sessionmaker,
    Session,
    Query,
)

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
    """Define common columns to mapped classes using this class as a base class."""

    @declared_attr.directive
    # Automaticaly create column name from class name
    def __tablename__(cls) -> str:
        return cls.__name__.lower()

    # Common columns
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(default=False)

    def soft_delete(self, db: Session):
        self.deleted_at = func.now()
        self.is_deleted = True
        db.commit()


file_workflow_association_table = Table(
    "file_workflow_association_table",
    BaseModel.metadata,
    Column("file_id", ForeignKey("file.id"), primary_key=True),
    Column("workflow_id", ForeignKey("workflow.id"), primary_key=True),
)


@event.listens_for(Query, "before_compile", retval=True)
def before_compile(query):
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

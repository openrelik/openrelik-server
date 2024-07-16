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
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    declared_attr,
    mapped_column,
    sessionmaker,
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


file_workflow_association_table = Table(
    "file_workflow_association_table",
    BaseModel.metadata,
    Column("file_id", ForeignKey("file.id"), primary_key=True),
    Column("workflow_id", ForeignKey("workflow.id"), primary_key=True),
)


# Database connection, used as a dependency inhjection.
def get_db_connection():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

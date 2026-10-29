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

import base64
import binascii
import datetime
import json
import os
import re
import uuid
from typing import Literal, get_args

from sqlalchemy import exists, func, literal, select, tuple_, union, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased, selectinload

from api.v1 import schemas
from config import config
from datastores.sql.models.file import File
from datastores.sql.models.folder import Folder
from datastores.sql.models.group import Group, GroupRole
from datastores.sql.models.role import Role
from datastores.sql.models.user import User, UserRole
from datastores.sql.models.workflow import Workflow


def _folder_list_options():
    """Eager-load options for folder listings (FolderResponseCompact).

    Loads the owner and workflows for all folders in two extra queries instead of one
    lazy load per folder (N+1). Only the workflow columns used in the response are loaded.
    """
    return (
        selectinload(Folder.user),
        selectinload(Folder.workflows).load_only(Workflow.id, Workflow.display_name),
    )


def _shared_folder_ids(current_user: User):
    """Build a subquery of IDs for folders shared with the user but not owned by them.

    Includes folders shared directly with the user and folders shared with any group the
    user is a member of. Built with Core select() on the role tables so that the soft-delete
    before_compile hook (which only applies to legacy Query objects) does not inject a stray
    FROM folder, which previously caused a cartesian product against the whole folder table.

    Args:
        current_user (User): current user

    Returns:
        Select statement with a single "id" column, for use with Folder.id.in_().
    """
    user_shared_ids = select(UserRole.folder_id.label("id")).where(
        UserRole.user_id == current_user.id,
        UserRole.role != Role.OWNER,
        UserRole.folder_id.is_not(None),
    )
    group_shared_ids = (
        select(GroupRole.folder_id.label("id"))
        .join(Group, Group.id == GroupRole.group_id)
        .where(
            Group.users.any(id=current_user.id),
            GroupRole.folder_id.is_not(None),
        )
    )
    shared_ids = union(user_shared_ids, group_shared_ids).subquery()
    # Exclude folders the user owns. NOT EXISTS lets the database use an anti-join; NOT IN
    # falls back to rescanning the owned IDs per row when they don't fit in work_mem.
    owner_role = aliased(UserRole, name="owner_role")
    is_owned = (
        exists()
        .where(
            owner_role.folder_id == shared_ids.c.id,
            owner_role.user_id == current_user.id,
            owner_role.role == Role.OWNER,
        )
    )
    return select(shared_ids.c.id).where(~is_owned)


def get_root_folders_from_db(db: Session, current_user: User):
    """Get all root folders for a user.

    Args:
        db (Session): database session
        current_user (User): current user

    Returns:
        list: list of folders
    """
    return (
        db.query(Folder)
        .join(UserRole, UserRole.folder_id == Folder.id)
        .filter(
            UserRole.user_id == current_user.id,
            UserRole.role == Role.OWNER,
            Folder.parent_id.is_(None),
        )
        .options(*_folder_list_options())
        .order_by(Folder.created_at.desc(), Folder.id.desc())
        .all()
    )


def get_shared_folders_from_db(db: Session, current_user: User):
    """Get all shared folders for a user.

    Args:
        db (Session): database session
        current_user (User): current user

    Returns:
        list: list of folders
    """
    return (
        db.query(Folder)
        .filter(Folder.id.in_(_shared_folder_ids(current_user)))
        .options(*_folder_list_options())
        .order_by(Folder.created_at.desc(), Folder.id.desc())
        .all()
    )


# Columns get_all_folders_from_db can sort by. Names sort case-insensitively.
FolderSortKey = Literal["created_at", "updated_at", "display_name"]
FolderSortOrder = Literal["asc", "desc"]
FOLDER_SORT_KEYS = get_args(FolderSortKey)
FOLDER_SORT_ORDERS = get_args(FolderSortOrder)

# Largest folder ID, the range of the BigInteger primary key.
_MAX_FOLDER_ID = 2**63 - 1


class InvalidCursorError(ValueError):
    """Raised when a folder listing cursor can't be decoded or doesn't match the listing."""


def _sort_column(sort: str):
    if sort == "display_name":
        return func.lower(Folder.display_name)
    return getattr(Folder, sort)


def encode_folder_cursor(
    folder: Folder, sort: str, order: str, search_term: str | None = None
) -> str:
    """Encode the position after folder in a listing sorted by sort and order.

    Args:
        folder (Folder): last folder of a page
        sort (str): sort key, one of FOLDER_SORT_KEYS
        order (str): "asc" or "desc"
        search_term (str | None): search term of the listing, if any

    Returns:
        str: opaque cursor for the next page
    """
    value = getattr(folder, sort)
    if isinstance(value, datetime.datetime):
        value = value.isoformat()
    payload = {
        "sort": sort,
        "order": order,
        "q": search_term or None,
        "value": value,
        "id": folder.id,
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _decode_folder_cursor(cursor: str, sort: str, order: str, search_term: str | None):
    """Decode a cursor from encode_folder_cursor into (value, id).

    Raises:
        InvalidCursorError: if the cursor is malformed or was made for another listing
            (another sort, order or search term).
    """
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        value, folder_id = payload["value"], payload["id"]
        listing = (payload["sort"], payload["order"], payload["q"])
        if sort == "display_name":
            if not isinstance(value, str):
                raise TypeError("display_name cursor value must be a string")
        else:
            value = datetime.datetime.fromisoformat(value)
    except (binascii.Error, ValueError, KeyError, TypeError, AttributeError) as e:
        raise InvalidCursorError("invalid cursor") from e
    # bool is a subclass of int, but not an ID.
    if (
        not isinstance(folder_id, int)
        or isinstance(folder_id, bool)
        or not 0 < folder_id <= _MAX_FOLDER_ID
    ):
        raise InvalidCursorError("invalid cursor")
    if listing != (sort, order, search_term or None):
        raise InvalidCursorError("cursor is for another listing (sort, order or search term)")
    return value, folder_id


def get_all_folders_from_db(
    db: Session,
    current_user: User,
    search_term: str | None = None,
    page: int = 1,
    page_size: int = 100,
    sort: FolderSortKey = "created_at",
    order: FolderSortOrder = "desc",
    after: str | None = None,
) -> tuple[list[Folder], int | None, str | None]:
    """
    Retrieves accessible folders with conditional logic based on search term.

    - If search_term is NOT provided (Default View):
        Returns user's owned root folders plus all directly shared folders
        (root and subfolders where share is explicit). Uses non-recursive logic.
    - If search_term IS provided (Recursive Search Mode):
        Uses recursive logic to find ALL accessible folders (direct/inherited,
        including root folders), and filters them by search term (case-insensitive).

    Args:
        db (Session): database session
        current_user (User): current user
        search_term (str | None, optional): Term to filter folder names by
        page (int, optional): Page number. Defaults to 1. Ignored when after is set.
        page_size (int, optional): Number of records per page.
        sort (str, optional): Sort key, one of FOLDER_SORT_KEYS. Defaults to created_at.
        order (str, optional): "asc" or "desc". Defaults to desc.
        after (str | None, optional): Cursor from a previous call; returns the folders
            after it instead of a page. Unlike page offsets, folders created or deleted
            while paging don't shift the remaining pages.

    Returns:
        tuple: the folders, the total count (None when after is set, as counting on
        every page is expensive), and a cursor for the next folders (None after the
        last ones).

    Raises:
        ValueError: if sort or order is not supported, page is below 1 or page_size is
            negative.
        InvalidCursorError: if after is malformed or was made for another listing.
    """
    if sort not in FOLDER_SORT_KEYS:
        raise ValueError(f"unsupported sort: {sort!r}")
    if order not in FOLDER_SORT_ORDERS:
        raise ValueError(f"unsupported order: {order!r}")
    if page < 1:
        raise ValueError(f"page must be 1 or more, not {page}")
    if page_size is not None and page_size < 0:
        raise ValueError(f"page_size must not be negative, not {page_size}")


    final_query = None

    if search_term:
        # --- Search Mode: Recursive CTE for ALL accessible folders (Root + Subfolders) ---

        # Step 1: Find IDs of Folders with DIRECT Access (Anchor Folders)
        owned_anchor_ids = (
            select(Folder.id)
            .join(UserRole)
            .filter(UserRole.user_id == current_user.id, UserRole.role == Role.OWNER)
        )
        direct_shared_anchor_ids = (
            select(Folder.id)
            .join(UserRole)
            .filter(UserRole.user_id == current_user.id, UserRole.role != Role.OWNER)
        )
        group_shared_anchor_ids = (
            select(Folder.id)
            .join(GroupRole)
            .join(Group)
            .filter(Group.users.any(id=current_user.id))
        )

        direct_access_folder_ids_query = union(
            owned_anchor_ids, direct_shared_anchor_ids, group_shared_anchor_ids
        )

        # Step 2: Define the Recursive CTE
        accessible_folders_cte = (
            select(Folder.id.label("id"))
            .filter(Folder.id.in_(direct_access_folder_ids_query))
            .cte(name="accessible_folders", recursive=True)
        )
        cte_alias = aliased(accessible_folders_cte, name="cte_alias")
        folder_alias = aliased(Folder, name="folder_alias")
        recursive_part = select(folder_alias.id).join(
            cte_alias, folder_alias.parent_id == cte_alias.c.id
        )
        accessible_folders_cte = accessible_folders_cte.union_all(recursive_part)

        # Step 3: Query Folders using the CTE and Apply Filters
        # The recursive CTE can reach the same folder through more than one path; IN
        # matches each folder once, without a DISTINCT that would restrict the ORDER BY.
        final_query = db.query(Folder).filter(
            Folder.id.in_(select(accessible_folders_cte.c.id))
        )

        # Apply Search Filter
        search_pattern = f"%{search_term}%"
        final_query = final_query.filter(Folder.display_name.ilike(search_pattern))

    else:
        # --- Default View: Non-Recursive - Owned Roots + Direct Shares ---

        # Root folders owned by the user. Joins folder for parent_id, the outer query can't
        # filter on it as the shared folders below include subfolders.
        owned_root_folder_ids = (
            select(UserRole.folder_id.label("id"))
            .join(Folder, Folder.id == UserRole.folder_id)
            .where(
                UserRole.user_id == current_user.id,
                UserRole.role == Role.OWNER,
                Folder.parent_id.is_(None),  # Owned ROOT only for default view
            )
        )
        # Combine owned roots and direct shares (root and subfolders) for the default view.
        # A single IN (UNION ...) instead of OR-ing two IN clauses, so the database can drive
        # the query from the ID set instead of filtering every row in the folder table.
        final_query = db.query(Folder).filter(
            Folder.id.in_(union(owned_root_folder_ids, _shared_folder_ids(current_user)))
        )

    if after:
        value, last_id = _decode_folder_cursor(after, sort, order, search_term)
        last_value = literal(value)
        if sort == "display_name":
            # The cursor holds the raw name, lowercased here by the database like the
            # sort column. Python's str.lower() differs for some names (e.g. "İ", final
            # sigma) and the database's depends on its locale, so a cursor lowercased in
            # Python could skip or repeat folders.
            last_value = func.lower(last_value)
        position = tuple_(_sort_column(sort), Folder.id)
        last = tuple_(last_value, literal(last_id))
        final_query = final_query.filter(position > last if order == "asc" else position < last)
        total_count = None
    else:
        # Get total count before applying ordering and pagination
        total_count = final_query.count()

    # --- Execute the selected query with pagination ---
    # Order by id as a tie-breaker to get stable pagination.
    final_query = final_query.order_by(
        getattr(_sort_column(sort), order)(), getattr(Folder.id, order)()
    ).options(*_folder_list_options())

    # Apply pagination. One extra row tells whether there is a next page.
    if page_size is None:
        return final_query.all(), total_count, None
    if not after:
        final_query = final_query.offset((page - 1) * page_size)
    folders = final_query.limit(page_size + 1).all()
    has_more = len(folders) > page_size
    folders = folders[:page_size]
    next_cursor = None
    # With page_size 0, the extra row leaves no folder to build a cursor from.
    if has_more and folders:
        next_cursor = encode_folder_cursor(folders[-1], sort, order, search_term)
    return folders, total_count, next_cursor


def get_subfolders_from_db(db: Session, parent_folder_id: str):
    """Get all folders in a folder

    Args:
        db (Session): database session
        folder_id (str): folder id

    Returns:
        list: list of folders
    """
    return (
        db.query(Folder)
        .filter_by(parent_id=parent_folder_id)
        .options(*_folder_list_options())
        .order_by(Folder.id.desc())
        .all()
    )


def get_folder_from_db(db: Session, folder_id: int):
    """Get a folder from the database by its ID.

    Args:
        db (Session): database session
        folder_id (int): folder id

    Returns:
        Folder object
    """
    return db.get(Folder, folder_id)


# Characters allowed in a normalized case reference.
_CASE_REF_PATTERN = re.compile(r"[a-z0-9._/-]+")
_CASE_REF_MAX_LENGTH = 255


class InvalidCaseRefError(ValueError):
    """Raised when a case reference is malformed or can't be set on a folder."""


class CaseRefTakenError(Exception):
    """Raised when another folder already has the case reference.

    Attributes:
        case_ref (str): the normalized case reference
        folder (Folder | None): the folder that has it, or None if it was gone by the time
            it was looked up
    """

    def __init__(self, case_ref: str, folder: Folder | None):
        super().__init__(f"case {case_ref} already exists")
        self.case_ref = case_ref
        self.folder = folder


def normalize_case_ref(case_ref: str) -> str:
    """Return the canonical form of a case reference.

    Trims surrounding whitespace, converts to lower case and replaces each run of inner
    whitespace with "-", so "CASE 123", "case-123" and " case-123 " are the same case.

    Args:
        case_ref (str): case reference as given by the user

    Returns:
        str: the normalized case reference

    Raises:
        InvalidCaseRefError: if the reference is empty, too long, has characters other
            than letters, digits, "-", "_", "." and "/" after normalization, doesn't start
            and end with a letter or digit, or has an empty, "." or ".." part between
            slashes. Those would be changed or merged in URLs (/folders/case/{case_ref}).
    """
    normalized = re.sub(r"\s+", "-", case_ref.strip().lower())
    if not normalized:
        raise InvalidCaseRefError("case reference must not be empty")
    if len(normalized) > _CASE_REF_MAX_LENGTH:
        raise InvalidCaseRefError(
            f"case reference must be at most {_CASE_REF_MAX_LENGTH} characters"
        )
    if not _CASE_REF_PATTERN.fullmatch(normalized):
        raise InvalidCaseRefError(
            "case reference can only contain letters a-z, digits, '-', '_', '.' and '/'"
        )
    if not (normalized[0].isalnum() and normalized[-1].isalnum()):
        raise InvalidCaseRefError("case reference must start and end with a letter or digit")
    if any(part in ("", ".", "..") for part in normalized.split("/")):
        raise InvalidCaseRefError(
            "case reference must not contain '//' or have '.' or '..' between slashes"
        )
    return normalized


def get_folder_by_case_ref_from_db(db: Session, case_ref: str):
    """Get the folder with a case reference.

    Args:
        db (Session): database session
        case_ref (str): case reference, normalized or not

    Returns:
        Folder object, or None if no folder has the reference

    Raises:
        InvalidCaseRefError: if the reference is malformed.
    """
    return _case_folder_query(db, normalize_case_ref(case_ref)).first()


def _case_folder_query(db: Session, case_ref: str):
    """Query the folder holding a normalized case reference."""
    # Filtering on NOT is_deleted, the condition of ix_folder_case_ref, lets Postgres use the
    # index. The soft-delete filter that db.query adds also allows NULL, so it doesn't.
    return db.query(Folder).filter(Folder.case_ref == case_ref, ~Folder.is_deleted)


def _is_case_ref_clash(error: IntegrityError) -> bool:
    """Return whether error is a violation of the unique case reference index."""
    # Postgres names the index, SQLite the column.
    message = str(error.orig)
    return "ix_folder_case_ref" in message or "folder.case_ref" in message


def _commit_case_ref(db: Session, case_ref: str | None):
    """Commit, turning a clash on the unique case reference into CaseRefTakenError."""
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        if not case_ref or not _is_case_ref_clash(e):
            raise
        existing = _case_folder_query(db, case_ref).first()
        raise CaseRefTakenError(case_ref, existing) from e


def set_folder_case_ref_in_db(db: Session, folder: Folder, case_ref: str | None):
    """Set or clear the case reference of a root folder.

    Setting the reference the folder already has changes nothing. The database's unique
    index decides between concurrent requests for the same reference.

    Args:
        db (Session): database session
        folder (Folder): root folder to update
        case_ref (str | None): case reference, normalized or not, or None to clear it

    Returns:
        Folder: the updated folder

    Raises:
        InvalidCaseRefError: if the reference is malformed or the folder is a subfolder.
        CaseRefTakenError: if another folder has the reference.
    """
    if case_ref is not None:
        case_ref = normalize_case_ref(case_ref)
        if folder.parent_id is not None:
            raise InvalidCaseRefError("only root folders can be case folders")
    if folder.case_ref == case_ref:
        return folder
    folder.case_ref = case_ref
    _commit_case_ref(db, case_ref)
    db.refresh(folder)
    return folder


def create_root_folder_in_db(
    db: Session,
    new_folder: schemas.FolderCreateRequest,
    current_user: User,
):
    """Create a folder

    Args:
        db (Session): database session
        folder (dict): dictionary for a folder
        current_user (User): current user

    Returns:
        Folder: folder
    """
    storage_provider_configs = config.get("server", {}).get("storage", {}).get("providers", {})
    default_provider_name = storage_provider_configs.get("default")

    # Set storage provider name from user request. If missing, use default provider.
    if new_folder.storage_provider:
        if new_folder.storage_provider not in storage_provider_configs:
            raise ValueError(f"Invalid storage provider: {new_folder.storage_provider}")
        storage_provider_name = new_folder.storage_provider
    else:
        storage_provider_name = default_provider_name

    case_ref = None
    if new_folder.case_ref is not None:
        case_ref = normalize_case_ref(new_folder.case_ref)

    new_db_folder = Folder(
        display_name=new_folder.display_name,
        uuid=uuid.uuid4(),
        user=current_user,
        parent_id=None,
        storage_provider=storage_provider_name,
        case_ref=case_ref,
    )
    db.add(new_db_folder)
    # The folder and its owner role are committed together, so a folder whose case
    # reference is taken leaves nothing behind.
    user_role = UserRole(user=current_user, folder=new_db_folder, role=Role.OWNER)
    db.add(user_role)
    _commit_case_ref(db, case_ref)
    db.refresh(new_db_folder)

    try:
        if not os.path.exists(new_db_folder.path):
            os.mkdir(new_db_folder.path)
    except Exception:
        # Don't leave a folder without a directory behind, holding its case reference.
        db.delete(user_role)
        db.delete(new_db_folder)
        db.commit()
        raise

    return new_db_folder


def create_subfolder_in_db(
    db: Session,
    folder_id: int,
    new_folder: schemas.FolderCreateRequest,
    current_user: User,
):
    """Create a folder

    Args:
        db (Session): database session
        folder_id (int): parent folder id
        new_folder (dict): dictionary for a folder
        current_user (User): current user

    Returns:
        Folder: folder
    """
    # By default, the storage provider is set to None, this will have the affect that the subfolder inherit
    # the storage provider from its parent folder.
    storage_provider_name = None

    # If the user request a specific storage provider, use it instead. This will make the subfolder use a different
    # storage provider than its parent folder.
    if new_folder.storage_provider:
        storage_provider_configs = config.get("server", {}).get("storage", {}).get("providers", {})
        if new_folder.storage_provider not in storage_provider_configs:
            raise ValueError(f"Invalid storage provider: {new_folder.storage_provider}")
        storage_provider_name = new_folder.storage_provider

    new_db_folder = Folder(
        display_name=new_folder.display_name,
        uuid=uuid.uuid4(),
        user=current_user,
        parent_id=folder_id,
        storage_provider=storage_provider_name,
    )
    db.add(new_db_folder)
    db.commit()
    db.refresh(new_db_folder)

    user_role = UserRole(user=current_user, folder=new_db_folder, role=Role.OWNER)
    db.add(user_role)
    db.commit()

    if not os.path.exists(new_db_folder.path):
        os.mkdir(new_db_folder.path)

    return new_db_folder


def update_folder_in_db(db: Session, folder: schemas.FolderUpdateRequest):
    """Update a folder in the database.

    Args:
        db (Session): SQLAlchemy session object
        folder (dict): Updated dictionary of a folder

    Returns:
        Folder object
    """
    folder_in_db = db.get(Folder, folder.id)
    folder_dict = folder.model_dump()
    for key, value in folder_dict.items():
        setattr(folder_in_db, key, value) if value else None
    db.commit()
    db.refresh(folder_in_db)
    return folder_in_db


def delete_folder_from_db(db: Session, folder_id: int) -> None:
    """
    Function to soft-delete a folder and all its descendant folders and files using a recursive CTE
    and bulk updates. Deleting a case folder frees its case reference for other folders, while
    the deleted folder keeps it as a record.

    Args:
        db (Session): A SQLAlchemy database session object.
        folder_id (int): The ID of the root folder to be deleted.
    """
    # Define the CTE to find all descendant folders including the starting one
    folder_cte = (
        select(Folder.id).where(Folder.id == folder_id).cte(name="folder_hierarchy", recursive=True)
    )

    # Alias for the CTE to use in the recursive part
    folder_alias = folder_cte.alias()
    folder_recursive_alias = Folder.__table__.alias()

    # Recursive part of the CTE
    folder_cte = folder_cte.union_all(
        select(folder_recursive_alias.c.id).where(
            folder_recursive_alias.c.parent_id == folder_alias.c.id
        )
    )

    # 1. Get all folder IDs to delete
    folder_ids_to_delete_stmt = select(folder_cte.c.id)
    folder_ids_result = db.execute(folder_ids_to_delete_stmt).scalars().all()

    if not folder_ids_result:
        return

    # 2. Bulk update files in these folders
    file_update_query = (
        update(File)
        .where(File.folder_id.in_(folder_ids_result))
        .values(is_deleted=True, deleted_at=func.now())
        # Important for bulk updates: prevents trying to sync ORM state
        .execution_options(synchronize_session=False)
    )
    db.execute(file_update_query)

    # 3. Bulk update the folders themselves
    folder_update_query = (
        update(Folder)
        .where(Folder.id.in_(folder_ids_result))
        .values(
            is_deleted=True,
            deleted_at=func.now(),
        )
        # Important for bulk updates: prevents trying to sync ORM state
        .execution_options(synchronize_session=False)
    )
    db.execute(folder_update_query)

    # 4. Commit the transaction
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise  # Re-raise the exception after rollback

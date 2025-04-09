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
import uuid

from sqlalchemy import and_, func, select, union, update
from sqlalchemy.orm import Session, aliased

from api.v1 import schemas
from datastores.sql.models.file import File
from datastores.sql.models.folder import Folder
from datastores.sql.models.group import Group, GroupRole
from datastores.sql.models.role import Role
from datastores.sql.models.user import User, UserRole


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
        .order_by(Folder.created_at.desc())
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
    # Get folders shared directly with the user
    user_folders = (
        db.query(Folder.id.label("id"))
        .join(UserRole, UserRole.folder_id == Folder.id)
        .filter(
            UserRole.user_id == current_user.id,
            UserRole.role != Role.OWNER,
        )
    )

    # Get folders shared with groups the user is a member of
    group_folders = (
        db.query(Folder.id.label("id"))
        .join(GroupRole, GroupRole.folder_id == Folder.id)
        .join(Group, Group.id == GroupRole.group_id)
        .filter(Group.users.any(id=current_user.id))
    )

    # Combine the results and exclude folders where the user is the owner
    shared_folders = user_folders.union(group_folders).subquery()

    return (
        db.query(Folder)
        .select_from(shared_folders)  # Use select_from to make the join explicit
        .join(Folder, Folder.id == shared_folders.c.id)  # Specify the join condition here
        .outerjoin(
            UserRole,
            and_(
                UserRole.folder_id == Folder.id,
                UserRole.user_id == current_user.id,
                UserRole.role == Role.OWNER,
            ),
        )
        .filter(UserRole.id.is_(None))
        .order_by(Folder.created_at.desc())
        .all()
    )


def get_all_folders_from_db(db: Session, current_user: User, search_term: str | None = None):
    """
    Retrieves accessible folders with conditional logic based on search term.

    - If search_term is NOT provided (Default View):
        Returns user's owned root folders plus all directly shared folders
        (root and subfolders where share is explicit). Uses non-recursive logic.
    - If search_term IS provided (Recursive Search Mode):
        Uses resursive logic to find ALL accessible folders (direct/inherited,
        including root folders), and filters them by search term (case-insensitive).

    Args:
        db (Session): database session
        current_user (User): current user
        search_term (str | None, optional): Term to filter folder names by

    Returns:
        list[Folder]: List of folders based on the mode, ordered by creation date desc.
    """

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
        # Join Folder with CTE results to get only accessible folders
        final_query = db.query(Folder).join(
            accessible_folders_cte, Folder.id == accessible_folders_cte.c.id
        )

        # Apply Search Filter (mandatory in this branch)
        search_pattern = f"%{search_term}%"
        final_query = final_query.filter(Folder.display_name.ilike(search_pattern))

    else:
        # --- Default View: Non-Recursive - Owned Roots + Direct Shares ---

        # Query for root folders owned by the user
        owned_root_folders_query = (
            db.query(Folder)
            .join(UserRole, UserRole.folder_id == Folder.id)
            .filter(
                UserRole.user_id == current_user.id,
                UserRole.role == Role.OWNER,
                Folder.parent_id.is_(None),  # Owned ROOT only for default view
            )
        )
        # Query for folders directly shared (not owned)
        user_shared_ids = (
            db.query(Folder.id.label("id"))
            .join(UserRole, UserRole.folder_id == Folder.id)
            .filter(
                UserRole.user_id == current_user.id,
                UserRole.role != Role.OWNER,
            )
        )
        group_shared_ids = (
            db.query(Folder.id.label("id"))
            .join(GroupRole, GroupRole.folder_id == Folder.id)
            .join(Group, Group.id == GroupRole.group_id)
            .filter(Group.users.any(id=current_user.id))
        )
        potentially_shared_folder_ids = user_shared_ids.union(group_shared_ids).subquery()
        shared_folders_query = (
            db.query(Folder)
            .select_from(potentially_shared_folder_ids)
            .join(Folder, Folder.id == potentially_shared_folder_ids.c.id)
            .outerjoin(
                UserRole,
                and_(
                    UserRole.folder_id == Folder.id,
                    UserRole.user_id == current_user.id,
                    UserRole.role == Role.OWNER,
                ),
            )
            .filter(UserRole.id.is_(None))
        )
        # Combine owned roots and direct shares using UNION for the default view
        final_query = owned_root_folders_query.union(shared_folders_query)

    # --- Execute the selected query ---
    return final_query.order_by(Folder.created_at.desc()).all()


def get_subfolders_from_db(db: Session, parent_folder_id: str):
    """Get all folders in a folder

    Args:
        db (Session): database session
        folder_id (str): folder id

    Returns:
        list: list of folders
    """
    return db.query(Folder).filter_by(parent_id=parent_folder_id).order_by(Folder.id.desc()).all()


def get_folder_from_db(db: Session, folder_id: int):
    """Get a folder from the database by its ID.

    Args:
        db (Session): database session
        folder_id (int): folder id

    Returns:
        Folder object
    """
    return db.get(Folder, folder_id)


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
    new_db_folder = Folder(
        display_name=new_folder.display_name,
        uuid=uuid.uuid4(),
        user=current_user,
        parent_id=None,
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
    new_db_folder = Folder(
        display_name=new_folder.display_name,
        uuid=uuid.uuid4(),
        user=current_user,
        parent_id=folder_id,
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


def delete_folder_from_db(db: Session, folder_id: int):
    """
    Function to soft-delete a folder and all its descendant folders and files using a recursive CTE
    and bulk updates.

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
        print(f"Folder with ID {folder_id} not found or has no descendants.")
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
        print(f"Soft deleted folder {folder_id} and its contents successfully.")
    except Exception as e:
        db.rollback()
        print(f"Error during bulk delete commit for folder {folder_id}: {e}")
        raise  # Re-raise the exception after rollback

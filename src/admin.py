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
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import typer
from argon2 import PasswordHasher
from rich import print
from rich.prompt import Prompt
from rich.table import Table
from sqlalchemy import and_, func, not_, select, update

from api.v1 import schemas
from auth.common import create_jwt_token, validate_jwt_token
from config import get_config
from datastores.sql import database
from datastores.sql.crud.group import (
    create_group_in_db,
    get_group_by_name_from_db,
    get_groups_from_db,
)
from datastores.sql.crud.user import (
    create_user_api_key_in_db,
    create_user_in_db,
    get_user_by_username_from_db,
    get_users_from_db,
)
from datastores.sql.crud.workflow import (
    delete_workflow_template_from_db,
    get_workflow_templates_from_db,
)
from datastores.sql.models.file import File
from datastores.sql.models.folder import Folder

# Import models to make the ORM register correctly.
from datastores.sql.models.role import Role
from datastores.sql.models.user import UserRole

password_hasher = PasswordHasher()

app = typer.Typer()


def get_username_and_password(
    username: Optional[str] = None, password: Optional[str] = None
) -> Tuple[str, str]:
    """Prompts the user for username and password, pre-filling if provided."""

    if username:
        print("[bold blue]Username: [/]", username)
    else:
        username = Prompt.ask("[bold blue]Enter username[/]")

    if not password:
        password = Prompt.ask("[bold blue]Enter password[/]", password=True)

    if not username or not password:
        print("[bold red]Error: Both username and password are required.[/bold red]")
        raise typer.Exit(code=1)
    return username, password


@app.command()
def create_user(
    username: Optional[str] = typer.Argument(None, help="Username for the new user."),
    password: Optional[str] = typer.Option(
        None, "--password", "-p", help="Password for the new user."
    ),
    admin: bool = typer.Option(False, "--admin", "-a", help="Make the user an admin."),
) -> None:
    """Creates a new user."""
    with database.SessionLocal() as db:
        # Check for existing user *before* potentially prompting
        if username and get_user_by_username_from_db(db, username):
            print("[bold red]Error: User already exists.[/bold red]")
            raise typer.Exit(code=1)

        # Get username and password, prompting if necessary
        if not username or not password:
            username, password = get_username_and_password(username, password)

        # Create the new user
        hashed_password = password_hasher.hash(password)
        new_user = schemas.UserCreate(
            display_name=username,
            username=username,
            password_hash=hashed_password,
            password_hash_algorithm="argon2id",
            auth_method="local",
            uuid=uuid.uuid4(),
            is_admin=admin,
        )
        create_user_in_db(db, new_user)
        print(f"User with username '{username}' created and password set.")


@app.command()
def change_password(
    username: Optional[str] = typer.Argument(None, help="Username of the user."),
    new_password: Optional[str] = typer.Option(
        None, "--password", "-p", help="New password for the user."
    ),
) -> None:
    """Changes the password of an existing user."""
    existing_user = None

    with database.SessionLocal() as db:
        # Check for existing user *before* potentially prompting
        if username:
            existing_user = get_user_by_username_from_db(db, username)
            if not existing_user:
                print("[bold red]Error: User does not exist.[/bold red]")
                raise typer.Exit(code=1)
            if existing_user.auth_method != "local":
                print("[bold red]Error: You can only change password for local users.[/bold red]")
                raise typer.Exit(code=1)

        # Get username and password, prompting if necessary
        if not username or not new_password:
            username, new_password = get_username_and_password(username, new_password)

        if not existing_user:
            existing_user = get_user_by_username_from_db(db, username)

        existing_user.password_hash = password_hasher.hash(new_password)
        db.add(existing_user)
        db.commit()
        print(f"Password updated for user '{username}'.")


@app.command()
def create_api_key(
    username: str = typer.Argument(None, help="User to create API key for."),
    key_name: str = typer.Option(..., "--key-name", "-n", help="Name for the API key."),
    key_description: Optional[str] = typer.Option(
        None, "--description", "-d", help="Description for the API key (optional)."
    ),
) -> None:
    """Create an API key for a user."""
    with database.SessionLocal() as db:
        # If username is not provided, prompt for it
        if not username:
            username = Prompt.ask("[bold blue]Enter username[/]")

        user = get_user_by_username_from_db(db, username)
        if not user:
            print(f"[bold red]Error: User with username '{username}' not found.[/bold red]")
            raise typer.Exit(code=1)

        current_config = get_config()
        TOKEN_EXPIRE_MINUTES = current_config["auth"]["jwt_header_default_refresh_expire_minutes"]
        refresh_token = create_jwt_token(
            audience="api-client",
            expire_minutes=TOKEN_EXPIRE_MINUTES,
            subject=user.uuid.hex,
            token_type="refresh",
        )
        payload = validate_jwt_token(
            refresh_token,
            expected_token_type="refresh",
            expected_audience="api-client",
        )
        new_api_key = schemas.UserApiKeyCreate(
            display_name=key_name,
            description=key_description or "",
            token_jti=payload["jti"],
            token_exp=payload["exp"],
            user_id=user.id,
        )
        create_user_api_key_in_db(db, new_api_key)

        print(refresh_token)


@app.command()
def set_admin(
    username: Optional[str] = typer.Argument(None, help="Username of the user."),
    admin: bool = typer.Option(
        True, "--admin/--no-admin", "-a/-na", help="Set admin status of the user."
    ),
) -> None:
    """Set or remove admin privileges for a user."""
    if not username:
        username = Prompt.ask("[bold blue]Enter username[/]")

    with database.SessionLocal() as db:
        existing_user = get_user_by_username_from_db(db, username)
        if not existing_user:
            print(f"[bold red]Error: User with username '{username}' not found.[/bold red]")
            raise typer.Exit(code=1)

        existing_user.is_admin = admin
        db.add(existing_user)
        db.commit()

        if admin:
            print(f"'{username}' is now an admin.")
        else:
            print(f"Admin privileges removed for '{username}'.")


@app.command()
def user_details(
    username: str = typer.Argument(..., help="Username of the user."),
) -> None:
    """Displays details of a user in a table."""
    with database.SessionLocal() as db:
        existing_user = get_user_by_username_from_db(db, username)
        if not existing_user:
            print(f"[bold red]Error: User with username '{username}' not found.[/bold red]")
            raise typer.Exit(code=1)

        table = Table(title=f"User Details: {username}")
        table.add_column("Attribute", style="cyan", width=12)
        table.add_column("Value", style="magenta")
        table.add_row("UUID", str(existing_user.uuid))
        table.add_row("Display Name", existing_user.display_name)
        table.add_row("Username", existing_user.username)
        table.add_row("Auth Method", existing_user.auth_method)
        table.add_row("Is Admin", str(existing_user.is_admin))

        print(table)


@app.command()
def list_users() -> None:
    """Displays a list of all users in a table."""
    with database.SessionLocal() as db:
        users = get_users_from_db(db)

        table = Table(title="List of Users")
        table.add_column("Username", style="green")
        table.add_column("Display Name", style="magenta")
        table.add_column("UUID", style="cyan")
        table.add_column("Is Admin", style="yellow")
        table.add_column("Is Active", style="yellow")
        table.add_column("Is Robot", style="yellow")
        table.add_column("Created", style="steel_blue")

        for user in users:
            table.add_row(
                user.username,
                user.display_name,
                str(user.uuid),
                str(user.is_admin),
                str(user.is_active),
                str(user.is_robot),
                str(user.created_at),
            )

        print(table)


@app.command()
def fix_ownership() -> None:
    """Fixes ownership by adding missing OWNER roles to Files and Folders."""
    with database.SessionLocal() as db:
        # Query for Files and Folders without an OWNER UserRole
        files_without_owner = (
            db.query(File)
            .filter(
                not_(
                    File.user_roles.any(
                        UserRole.role == Role.OWNER
                    )  # Check if any UserRole has Role.OWNER
                )
            )
            .all()
        )

        folders_without_owner = (
            db.query(Folder)
            .filter(
                not_(
                    Folder.user_roles.any(
                        UserRole.role == Role.OWNER
                    )  # Check if any UserRole has Role.OWNER
                )
            )
            .all()
        )

        # Add OWNER UserRole to the queried Files and Folders
        for file_obj in files_without_owner:
            owner_role = UserRole(user=file_obj.user, role=Role.OWNER)
            db.add(owner_role)
            file_obj.user_roles.append(owner_role)

        for folder_obj in folders_without_owner:
            owner_role = UserRole(user=folder_obj.user, role=Role.OWNER)
            db.add(owner_role)
            folder_obj.user_roles.append(owner_role)

        # Commit the changes to the database
        db.commit()

        print(
            f"Added missing OWNER roles to {len(files_without_owner)} files and {len(folders_without_owner)} folders."
        )


@app.command()
def list_workflow_templates() -> None:
    """Lists all workflow templates in a table."""
    with database.SessionLocal() as db:
        templates = get_workflow_templates_from_db(db)

        table = Table(title="List of Workflow Templates")
        table.add_column("Workflow template ID", style="cyan")
        table.add_column("Display Name", style="green")
        table.add_column("Description", style="magenta")
        table.add_column("spec_json", style="cyan")
        table.add_column("username", style="green")

        for template in templates:
            table.add_row(
                str(template.id),
                template.display_name,
                template.description,
                template.spec_json,
                template.user.username,
            )

        print(table)


@app.command()
def purge_deleted_files(
    force: bool = typer.Option(False, "--force", "-f", help="Purge files without asking."),
    retention: Optional[str] = typer.Option(
        None,
        "--older-than",
        help="Purge files older than this duration (e.g., '10D', '2W', '1M', '6h').",
    ),
    batch_size: int = typer.Option(
        1000, "--batch-size", "-b", help="Number of files to process per batch."
    ),
) -> None:
    """
    Permanently deletes files marked as deleted from the filesystem.
    """
    db = database.SessionLocal()

    def _parse_retention_time(retention: str) -> timedelta:
        """Parses the retention time string (e.g., '10D', '2W', '1M') into a timedelta."""
        match = re.match(r"(\d+)([mhDWMY])", retention)
        if not match:
            raise typer.BadParameter("Invalid retention time format. Use <number>[m|h|D|W|M|Y].")
        value = int(match.group(1))
        unit = match.group(2)
        if unit == "m":
            return timedelta(minutes=value)
        if unit == "h":
            return timedelta(hours=value)
        elif unit == "D":
            return timedelta(days=value)
        elif unit == "W":
            return timedelta(weeks=value)
        elif unit == "M":
            return timedelta(days=value * 30)  # Approx
        elif unit == "Y":
            return timedelta(days=value * 365)  # Approx
        raise typer.BadParameter(f"Invalid retention time unit: {unit}")

    def _format_size(size_bytes):
        """Formats bytes into a human-readable string."""
        if size_bytes is None or size_bytes == 0:
            return "0 bytes"
        units = ["bytes", "KB", "MB", "GB", "TB", "PB"]
        i = 0
        size_bytes = float(size_bytes)
        while size_bytes >= 1024 and i < len(units) - 1:
            size_bytes /= 1024
            i += 1
        return f"{size_bytes:.2f} {units[i]}"

    base_storage_path = None
    try:
        # Load Config for Storage Path
        try:
            current_config = get_config()
            base_storage_path = current_config.get("server").get("storage_path")
            if not base_storage_path:
                print(
                    "[bold red]Error: Could not retrieve 'storage_path' from server configuration.[/bold red]"
                )
                return  # Exit if path is missing
        except Exception as config_e:
            print(f"[bold red]Error loading configuration: {config_e}[/bold red]")
            return

        # 1. Build Base Query Filter based on Retention and Purge Status
        filters = [File.is_deleted == True, File.is_purged == False]
        if retention:
            try:
                retention_delta = _parse_retention_time(retention)
                cutoff_time = datetime.now(timezone.utc) - retention_delta
                filters.append(File.deleted_at <= cutoff_time)
                print(
                    f"Applying retention filter: Purging files deleted on or before {cutoff_time.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                )
            except typer.BadParameter as e:
                print(f"[bold red]Error:[/bold red] {e}")
                return

        # 2. Get Summary
        summary_query = select(func.count(File.id), func.sum(File.filesize)).where(and_(*filters))
        num_files, total_size = db.execute(summary_query).first()
        total_size = total_size or 0

        if not num_files or num_files == 0:
            print("[bold green]No files matching criteria are waiting for purging.[/bold green]")
            return

        print("[bold blue]Purge request summary:[/bold blue]")
        print(f"  Number of files to purge: [bold]{num_files}[/bold]")
        print(f"  Total size: [bold]{_format_size(total_size)}[/bold]")

        # 3. Confirmation from the user
        if not force and not typer.confirm(
            f"Are you sure you want to permanently delete {num_files} files from the filesystem and database?"
        ):
            print("[bold red]Purge cancelled.[/bold red]")
            return

        # 4. Process in Batches
        print(f"[bold yellow]Starting purge process in batches of {batch_size}...[/bold yellow]")
        processed_count = 0
        all_successfully_purged_ids = []

        # Build query to fetch files to delete
        files_to_process_query = (
            select(File.id, File.uuid, File.extension, File.folder_id)
            .where(and_(*filters))
            .order_by(File.id)
            .execution_options(stream_results=True, yield_per=batch_size)
        )

        try:
            folder_paths_cache = {}  # Cache folder paths
            for batch in db.execute(files_to_process_query).partitions():
                # IDs successfully handled in filesystem for this specific batch
                batch_ids_processed_in_fs = []

                # Pre-fetch folder components for this batch
                folder_ids_in_batch = {
                    folder_id for _, _, _, folder_id in batch if folder_id is not None
                }
                new_folder_ids = folder_ids_in_batch - folder_paths_cache.keys()
                if new_folder_ids:
                    folder_components_results = db.execute(
                        select(Folder.id, Folder.uuid).where(Folder.id.in_(new_folder_ids))
                    ).all()

                    # Reconstruct path using config and cache it
                    for f_id, f_uuid in folder_components_results:
                        if f_uuid:
                            reconstructed_path = os.path.join(base_storage_path, f_uuid.hex)
                            folder_paths_cache[f_id] = reconstructed_path
                        else:
                            print(f"Warning: Folder ID {f_id} has no UUID. Cannot determine path.")
                            folder_paths_cache[f_id] = None

                # Delete files from the filesystem in the batch
                for file_id, file_uuid, file_extension, folder_id in batch:
                    processed_count += 1
                    actual_file_path = None
                    # Reconstruct the file path manually
                    if file_uuid and folder_id and folder_id in folder_paths_cache:
                        folder_path = folder_paths_cache[folder_id]
                        if folder_path:
                            base_filename = file_uuid.hex
                            filename = (
                                f"{base_filename}.{file_extension}"
                                if file_extension
                                else base_filename
                            )
                            actual_file_path = os.path.join(folder_path, filename)

                    file_removed_successfully = False
                    if actual_file_path and os.path.exists(actual_file_path):
                        try:
                            os.remove(actual_file_path)
                            file_removed_successfully = True
                        except OSError as e:
                            print(
                                f"[bold red]Error removing file {actual_file_path} (ID: {file_id}): {e}. Skipping DB purge.[/bold red]"
                            )
                    elif not actual_file_path:
                        print(
                            f"Skipping FS removal for File ID {file_id} due to missing path info."
                        )
                    else:  # Path constructed but file doesn't exist
                        print(
                            f"Warning: Filesystem file not found: {actual_file_path} (ID: {file_id}). Assuming removed."
                        )
                        file_removed_successfully = True

                    if file_removed_successfully:
                        batch_ids_processed_in_fs.append(file_id)

                # Add successfully deleted IDs from this batch to the main list
                all_successfully_purged_ids.extend(batch_ids_processed_in_fs)
                print(f"  Batch processed: {processed_count}/{num_files} files deleted.")

        except Exception as loop_e:
            # Catch errors during the cursor iteration or FS processing
            print(f"[bold red]ERROR during file processing loop: {loop_e}[/bold red]")
            raise loop_e

        # 5. Perform ONE Bulk Update and Commit AFTER the loop
        if all_successfully_purged_ids:
            try:
                update_query = (
                    update(File)
                    .where(File.id.in_(all_successfully_purged_ids))
                    .values(
                        is_purged=True,
                        purged_at=func.now(),
                    )
                    .execution_options(synchronize_session=False)
                )
                # Execute the single bulk update
                db.execute(update_query)

                # Commit the single transaction
                db.commit()
                print("Database updates committed [bold green]successfully[/bold green].")

            except Exception as final_commit_e:
                print(
                    f"[bold red]Error during final database update/commit. Rolling back: {final_commit_e}[/bold red]"
                )
                db.rollback()
                # Re-raise the error after rollback
                raise final_commit_e
        else:
            print(
                "No files required database update (none were successfully processed on filesystem)."
            )

        # Final Summary
        total_successfully_purged = len(all_successfully_purged_ids)
        print(f"[bold green]Successfully[/bold green] purged {total_successfully_purged} files")
        if processed_count != total_successfully_purged:
            print(
                f"[bold yellow]Note: {processed_count - total_successfully_purged} files encountered errors during filesystem removal or had missing info.[/bold yellow]"
            )

    # --- Outer Exception Handling ---
    except Exception as outer_e:
        # Catches errors from setup (config, summary query) or errors re-raised from inner blocks
        print(
            f"[bold red]An unexpected error occurred during the purge process: {outer_e}[/bold red]"
        )
        # Rollback any potential transaction state if an error occurred before final commit attempt
        db.rollback()
    finally:
        # --- Always close the DB Session ---
        if db:
            db.close()


@app.command()
def delete_workflow_template(
    template_id: int = typer.Argument(help="The workflow template ID to delete."),
) -> None:
    """Deletes a workflow template from the database."""
    with database.SessionLocal() as db:
        try:
            delete_workflow_template_from_db(db, template_id)
            print(f"Workflow template with ID {template_id} has been deleted.")
        except ValueError as e:
            print(f"Error: {e}")


@app.command()
def list_groups():
    """Lists all groups in a table."""
    with database.SessionLocal() as db:
        groups = get_groups_from_db(db)
        table = Table(title="List of Groups")
        table.add_column("Group Name", style="green")
        table.add_column("Description", style="magenta")
        table.add_column("Number of users", style="yellow")
        table.add_column("Created")
        for group in groups:
            table.add_row(
                group.name, group.description, str(len(group.users)), str(group.created_at)
            )
        print(table)


@app.command()
def create_group(
    group_name: str = typer.Argument(..., help="Name of the group to create."),
    description: str = typer.Option("", "--description", "-d", help="Description of the group."),
):
    """Creates a new group."""
    with database.SessionLocal() as db:
        group = get_group_by_name_from_db(db, group_name)
        if group:
            print(f"Group '{group_name}' already exists.")
            raise typer.Exit(code=1)
        new_group = schemas.GroupCreate(name=group_name, description=description)
        create_group_in_db(db, new_group)
        print(f"Group '{group_name}' created")


@app.command()
def rename_group(
    old_group_name: str = typer.Argument(..., help="Old name of the group."),
    new_group_name: str = typer.Argument(..., help="New name of the group."),
):
    """Renames an existing group."""
    with database.SessionLocal() as db:
        group = get_group_by_name_from_db(db, old_group_name)
        if not group:
            print(f"Group '{old_group_name}' not found.")
            raise typer.Exit(code=1)

        group.name = new_group_name
        db.commit()
        print(f"Group '{old_group_name}' renamed to '{new_group_name}'.")


@app.command()
def add_users_to_group(
    group_name: str = typer.Argument(..., help="Name of the group."),
    usernames: str = typer.Argument(..., help="List of usernames to add to the group."),
):
    """Adds a list of users to a group."""
    with database.SessionLocal() as db:
        group = get_group_by_name_from_db(db, group_name)
        if not group:
            print(f"Group '{group_name}' not found.")
            raise typer.Exit(code=1)

        for username in usernames.split(","):
            user = get_user_by_username_from_db(db, username)
            if not user:
                print(f"User '{username}' not found.")
                continue

            if user in group.users:
                print(f"User '{username}' is already in group '{group_name}'.")
                continue

            group.users.append(user)
            print(f"User '{username}' added to group '{group_name}'.")

        db.commit()


if __name__ == "__main__":
    app()

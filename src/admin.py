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

import uuid
from typing import Optional, Tuple

import typer
from argon2 import PasswordHasher
from rich import print
from rich.prompt import Prompt
from rich.table import Table
from sqlalchemy import not_

from api.v1 import schemas
from auth.common import create_jwt_token, validate_jwt_token
from config import get_config
from datastores.sql import database
from datastores.sql.crud.user import (
    create_user_api_key_in_db,
    create_user_in_db,
    get_user_by_username_from_db,
    get_users_from_db,
)
from datastores.sql.crud.workflow import (
    get_workflow_templates_from_db,
    delete_workflow_template_from_db,
)

# Import models to make the ORM register correctly.
from datastores.sql.models import file, folder, user, workflow
from datastores.sql.models.role import Role
from datastores.sql.models.user import UserRole

from datastores.sql.models.file import File
from datastores.sql.models.folder import Folder


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
):
    """Creates a new user."""
    db = database.SessionLocal()

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
):
    """Changes the password of an existing user."""
    db = database.SessionLocal()
    existing_user = None

    # Check for existing user *before* potentially prompting
    if username:
        existing_user = get_user_by_username_from_db(db, username)
        if not existing_user:
            print("[bold red]Error: User does not exist.[/bold red]")
            raise typer.Exit(code=1)
        if existing_user.auth_method != "local":
            print(
                "[bold red]Error: You can only change password for local users.[/bold red]"
            )
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
):
    """Create an API key for a user."""
    db = database.SessionLocal()

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
):
    """Set or remove admin privileges for a user."""
    db = database.SessionLocal()

    if not username:
        username = Prompt.ask("[bold blue]Enter username[/]")

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
):
    """Displays details of a user in a table."""
    db = database.SessionLocal()

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
def list_users():
    """Displays a list of all users in a table."""
    db = database.SessionLocal()
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
def fix_ownership():
    """Fixes ownership by adding missing OWNER roles to Files and Folders."""
    db = database.SessionLocal()

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
def list_workflow_templates():
    """Lists all workflow templates in a table."""
    db = database.SessionLocal()

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
def delete_workflow_template(
    template_id: int = typer.Argument(help="The workflow template ID to delete."),
):
    """Deletes a workflow template from the database."""
    db = database.SessionLocal()

    try:
        delete_workflow_template_from_db(db, template_id)
        print(f"Workflow template with ID {template_id} has been deleted.")
    except ValueError as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    app()

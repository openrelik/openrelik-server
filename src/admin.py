import uuid
from typing import Optional, Tuple

import typer
from rich import print
from rich.table import Table
from argon2 import PasswordHasher
from rich.prompt import Prompt

from api.v1 import schemas

# Import models to make the ORM register correctly.
from datastores.sql import database
from datastores.sql.crud.user import (
    create_user_in_db,
    get_user_by_username_from_db,
    get_users_from_db,
)
from datastores.sql.models import file, folder, user, workflow

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
        auth_method="local",
        uuid=uuid.uuid4(),
        is_admin=admin,
        password_hash=hashed_password,
        password_hash_algorithm="argon2id",
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
    # Add more rows for other attributes as needed

    print(table)


@app.command()
def list_users():
    """Displays a list of all users in a table."""
    db = database.SessionLocal()
    users = get_users_from_db(db)

    table = Table(title="List of Users")
    table.add_column("UUID", style="cyan")
    table.add_column("Display Name", style="magenta")
    table.add_column("Username", style="green")
    table.add_column("Is Admin", style="yellow")
    table.add_column("Is Active", style="yellow")
    table.add_column("Is Robot", style="yellow")

    for user in users:
        table.add_row(
            str(user.uuid),
            user.display_name,
            user.username,
            str(user.is_admin),
            str(user.is_active),
            str(user.is_robot),
        )

    print(table)


if __name__ == "__main__":
    app()

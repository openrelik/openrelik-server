import pytest
import sys
from unittest.mock import MagicMock, patch
from sqlalchemy.exc import ProgrammingError
from fastapi import FastAPI
from datastores.sql.models.user import User
from datastores.sql.models.group import Group
import api.v1.schemas as schemas

# Mock celery_utils before importing main to prevent network requests during tests.
with patch("lib.celery_utils.update_task_queues"):
    from main import populate_everyone_group, lifespan


@pytest.mark.asyncio
async def test_populate_everyone_group_new_group(mocker):
    db_mock = MagicMock()
    # get_group_by_name_from_db returns None
    mocker.patch("main.get_group_by_name_from_db", return_value=None)

    mock_group = Group(id=1, name="Everyone")
    mocker.patch("main.create_group_in_db", return_value=mock_group)

    user_mock = User(id=1)

    # Mocking query chain
    query_mock = MagicMock()
    filter_mock = MagicMock()
    all_mock = MagicMock()

    db_mock.query.return_value = query_mock
    query_mock.filter.return_value = filter_mock
    filter_mock.all.return_value = [user_mock]

    add_user_mock = mocker.patch("main.add_user_to_group")

    await populate_everyone_group(db_mock)

    add_user_mock.assert_called_once_with(db_mock, mock_group, user_mock)


@pytest.mark.asyncio
async def test_populate_everyone_group_existing_group(mocker):
    db_mock = MagicMock()
    mock_group = Group(id=1, name="Everyone")
    mocker.patch("main.get_group_by_name_from_db", return_value=mock_group)

    # Mocking query chain
    query_mock = MagicMock()
    filter_mock = MagicMock()

    db_mock.query.return_value = query_mock
    query_mock.filter.return_value = filter_mock
    filter_mock.all.return_value = []

    add_user_mock = mocker.patch("main.add_user_to_group")

    await populate_everyone_group(db_mock)

    add_user_mock.assert_not_called()


@pytest.mark.asyncio
async def test_lifespan_success(mocker):
    app = FastAPI()
    db_mock = MagicMock()
    session_local_mock = mocker.patch("main.SessionLocal", return_value=db_mock)
    populate_mock = mocker.patch("main.populate_everyone_group")

    async with lifespan(app):
        pass

    db_mock.execute.assert_called_once()
    populate_mock.assert_called_once_with(db_mock)
    db_mock.close.assert_called_once()


@pytest.mark.asyncio
async def test_lifespan_programming_error(mocker):
    app = FastAPI()
    db_mock = MagicMock()
    db_mock.execute.side_effect = ProgrammingError("statement", "params", "orig")
    session_local_mock = mocker.patch("main.SessionLocal", return_value=db_mock)
    populate_mock = mocker.patch("main.populate_everyone_group")

    async with lifespan(app):
        pass

    db_mock.execute.assert_called_once()
    populate_mock.assert_not_called()
    db_mock.close.assert_called_once()


def test_app_configuration():
    with patch("lib.celery_utils.update_task_queues"):
        from main import app, api_v1
    assert app is not None
    assert api_v1 is not None

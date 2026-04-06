# Copyright 2026 Google LLC
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

import asyncio
import datetime
import pytest

from lib.stream_manager import StreamSession, StreamManager


@pytest.mark.asyncio
async def test_stream_session_touch(mocker):
    """Test StreamSession.touch updates last_accessed."""
    mock_task = mocker.MagicMock(spec=asyncio.Task)
    session = StreamSession(session_id="test_session", task=mock_task)

    old_accessed = session.last_accessed
    # Small sleep to ensure time moves forward
    await asyncio.sleep(0.001)
    session.touch()

    assert session.last_accessed > old_accessed


@pytest.mark.asyncio
async def test_stream_session_broadcast(mocker):
    """Test StreamSession.broadcast sends message to listeners."""
    mock_task = mocker.MagicMock(spec=asyncio.Task)
    session = StreamSession(session_id="test_session", task=mock_task)

    queue1 = await session.add_listener()
    queue2 = await session.add_listener()

    await session.broadcast("test message")

    assert await queue1.get() == "test message"
    assert await queue2.get() == "test message"


@pytest.mark.asyncio
async def test_stream_session_remove_listener(mocker):
    """Test StreamSession.remove_listener."""
    mock_task = mocker.MagicMock(spec=asyncio.Task)
    session = StreamSession(session_id="test_session", task=mock_task)

    queue = await session.add_listener()
    assert len(session.listeners) == 1

    session.remove_listener(queue)
    assert len(session.listeners) == 0


def test_stream_manager_create_session(mocker):
    """Test StreamManager.create_session."""
    manager = StreamManager(ttl_days=1)
    mock_task = mocker.MagicMock(spec=asyncio.Task)

    session = manager.create_session(session_id="session1", task=mock_task)

    assert "session1" in manager.sessions
    assert manager.sessions["session1"] == session


def test_stream_manager_get_session(mocker):
    """Test StreamManager.get_session."""
    manager = StreamManager(ttl_days=1)
    mock_task = mocker.MagicMock(spec=asyncio.Task)
    session = manager.create_session(session_id="session1", task=mock_task)

    retrieved = manager.get_session("session1")
    assert retrieved == session


def test_stream_manager_remove_session(mocker):
    """Test StreamManager.remove_session."""
    manager = StreamManager(ttl_days=1)
    mock_task = mocker.MagicMock(spec=asyncio.Task)
    manager.create_session(session_id="session1", task=mock_task)

    manager.remove_session("session1")
    assert "session1" not in manager.sessions


def test_stream_manager_cleanup(mocker):
    """Test StreamManager.cleanup removes stale sessions."""
    # Create a manager with 0 TTL to make sessions immediately stale
    manager = StreamManager(ttl_days=0)
    mock_task = mocker.MagicMock(spec=asyncio.Task)
    mock_task.done.return_value = False

    session = manager.create_session(session_id="stale_session", task=mock_task)

    # Manually set last_accessed to the past to simulate passing of time
    session.last_accessed = datetime.datetime.now(
        datetime.timezone.utc
    ) - datetime.timedelta(days=1)

    manager.cleanup()

    assert "stale_session" not in manager.sessions
    mock_task.cancel.assert_called_once()

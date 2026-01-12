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

# This module implements a stream manager for handling SSE streams for
# long-running tasks. It uses asyncio to manage the streams and provides
# a simple interface for adding and removing listeners. It support sessions
# with a configurable time-to-live (TTL) and provides methods for broadcasting
# messages to all active listeners.

import asyncio
import datetime
import logging
from typing import Dict, Optional

# Configure logging
logger = logging.getLogger(__name__)


class StreamSession:
    """A stream session."""

    def __init__(self, session_id: str, task: asyncio.Task):
        self.session_id = session_id
        self.task = task
        self.listeners: set[asyncio.Queue] = set()
        self.created_at = datetime.datetime.now(datetime.timezone.utc)
        self.last_accessed = datetime.datetime.now(datetime.timezone.utc)

    def touch(self):
        """Touch the session to extend its TTL."""
        self.last_accessed = datetime.datetime.now(datetime.timezone.utc)
        logger.info(f"Touched session: {self.session_id}")

    async def broadcast(self, message: str):
        """Broadcast a message to all active listeners."""
        self.touch()
        for queue in list(self.listeners):
            await queue.put(message)
            logger.info(f"Broadcasted message to session: {self.session_id}")

    async def add_listener(self) -> asyncio.Queue:
        """Add a new listener."""
        self.touch()
        queue = asyncio.Queue()
        self.listeners.add(queue)
        logger.info(f"Added listener to session: {self.session_id}")
        return queue

    def remove_listener(self, queue: asyncio.Queue):
        """Remove a listener."""
        self.listeners.discard(queue)
        logger.info(f"Removed listener from session: {self.session_id}")


class StreamManager:
    """A stream manager."""

    def __init__(self, ttl_days: int = 2):
        """Initialize the stream manager.

        Args:
            ttl_days: The time-to-live for sessions in days.
        """
        self.sessions: Dict[str, StreamSession] = {}
        self.ttl = datetime.timedelta(days=ttl_days)

    def create_session(self, session_id: str, task: asyncio.Task) -> StreamSession:
        """Create a new session.

        Args:
            session_id: The ID of the session.
            task: The task associated with the session.

        Returns:
            StreamSession: The created session.
        """
        self.cleanup()
        session = StreamSession(session_id, task)
        self.sessions[session_id] = session
        logger.info(f"Created session: {session_id}")
        return session

    def get_session(self, session_id: str) -> Optional[StreamSession]:
        """Get a session by ID.

        Args:
            session_id: The ID of the session.

        Returns:
            Optional[StreamSession]: The session, or None if not found.
        """
        self.cleanup()
        session = self.sessions.get(session_id)
        if session:
            session.touch()
        return session

    def remove_session(self, session_id: str):
        """Remove a session by ID.

        Args:
            session_id: The ID of the session.
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Removed session: {session_id}")

    def cleanup(self):
        """Cleanup stale sessions."""
        now = datetime.datetime.now(datetime.timezone.utc)
        keys_to_delete = []
        for session_id, session in self.sessions.items():
            if now - session.last_accessed > self.ttl:
                keys_to_delete.append(session_id)

        for key in keys_to_delete:
            session = self.sessions.pop(key)
            if not session.task.done():
                session.task.cancel()
            logger.info(f"Cleaned up stale session: {key}")


# Global instance
stream_manager = StreamManager()

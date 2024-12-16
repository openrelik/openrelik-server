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
"""Tests OpenRelik API server."""

import unittest
from fastapi import testclient, FastAPI
import sys
import uuid
import mock
from api.v1 import configs
from api.v1 import folders
from fastapi import Depends
from api.v1 import schemas
from auth import common
from datastores.sql.database import get_db_connection
from sqlalchemy import create_engine, Table
from sqlalchemy.orm import Session
from datastores.sql.models.user import User
from datastores.sql.models.folder import Folder


def get_current_user():
    return True


def get_current_active_user():
    return True


def fake_get_db_connection():
    engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False}
                           )
    session = Session(engine)
    # create tables
    # >>> Base.metadata.create_all(engine)
    t = Table()

    t.create()

    # create objects needed for tests using models
    folder = Folder(
        display_name='test',
        uuid=uuid.uuid4(),
        user=User(),
        parent_id=None,
    )
    session.add(folder)
    session.commit()
    return session


class ApiServerTests(unittest.TestCase):

    EXPECTED_SYSTEM_CONFIG = {'active_llms': [], 'active_cloud': {
    }, 'allowed_data_types_preview': ['openrelik:hayabusa:html_report']}

    def _setup_api(self, route):
        # Include configs router for system config
        self.api.include_router(configs.router)
        # Override FastAPI dependency injections for authentication and Database.
        self.api.dependency_overrides[common.get_current_user] = get_current_user
        self.api.dependency_overrides[common.get_current_active_user] = get_current_active_user
        self.api.dependency_overrides[get_db_connection] = fake_get_db_connection
        self.api.include_router(
            globals()[route].router,
            prefix="/" + route,
            tags=[route],
        )

    def setUp(self):
        self.api = FastAPI()
        self.client = testclient.TestClient(self.api)

    def test_get_configs_system(self):
        self._setup_api("configs")
        response = self.client.get("/configs/system/")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), dict)
        self.assertEqual(response.json(), self.EXPECTED_SYSTEM_CONFIG)

    def test_get_root_folder(self):
        self._setup_api("folders")
        response = self.client.get("/folders/root")
        # self.assertEqual(response.status_code, 200)
        # self.assertIsInstance(response.json(), dict)
        print(response.json())


if __name__ == '__main__':
    unittest.main()

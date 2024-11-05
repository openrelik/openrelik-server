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

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.v1 import schemas
from datastores.sql.database import get_db_connection
from datastores.sql.models.group import Group

router = APIRouter()


@router.get("/")
def get_all_groups(
    db: Session = Depends(get_db_connection),
) -> List[schemas.GroupResponse]:
    """
    Get all groups.

    Args:
        db (Session): The database session.

    Returns:
        List of groups.
    """
    return db.query(Group).all()

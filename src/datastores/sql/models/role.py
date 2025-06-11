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
"""
Defines the Roles enum. The actual models for UserRole and GroupRole are defined in
user.py and group.py respectively.
"""
import enum


class Role(enum.Enum):
    """Represents a role in the database."""

    OWNER = "Owner"
    EDITOR = "Editor"
    VIEWER = "Viewer"
    NO_ACCESS = "No Access"

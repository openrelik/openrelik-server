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

from typing import Optional

from sqlalchemy.orm import Mapped, mapped_column

from sqlalchemy import UnicodeText

from ..database import BaseModel


class ExternalStorage(BaseModel):
    """Represents a read-only external storage location.

    External storages are host/container mount points (e.g. SMB or NFS shares)
    that already contain files which should be referenced by the platform without
    copying data into the main storage volume.

    Attributes:
        name (str): Unique logical identifier, e.g. "case_smb_storage".
        mount_point (str): Absolute path on the host/container, e.g. "/mnt/cases".
        description (Optional[str]): Human-readable description of this storage.
    """

    name: Mapped[str] = mapped_column(UnicodeText, index=True, unique=True)
    mount_point: Mapped[str] = mapped_column(UnicodeText, index=False)
    description: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False, nullable=True)

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

from fastapi import APIRouter

from config import config, get_active_llms


router = APIRouter()


@router.get("/system/")
def get_system_config():
    active_llms = get_active_llms()

    # Data types that will be allowed to be returned as unescaped HTML for use in
    # sandboxed iframe preview.
    allowed_data_types_preview = config.get("ui", {}).get(
        "allowed_data_types_preview", []
    )

    return {
        "active_llms": active_llms,
        "allowed_data_types_preview": allowed_data_types_preview,
    }

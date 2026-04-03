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

import pytest
import uuid
from datastores.sql.crud.workflow import (
    get_workflow_from_db,
    delete_workflow_from_db,
    get_file_workflows_from_db,
    get_folder_workflows_from_db,
    create_workflow_in_db,
    update_workflow_in_db,
    delete_workflow_template_from_db,
    get_workflow_template_from_db,
    create_workflow_template_in_db,
    update_workflow_template_in_db,
    get_task_from_db,
    get_task_by_uuid_from_db,
    create_task_in_db,
    create_task_report_in_db,
    get_workflow_templates_from_db,
)
from datastores.sql.models.workflow import Workflow, WorkflowTemplate, Task, TaskReport

def test_get_workflow_from_db(mocker):
    """Test get_workflow_from_db."""
    mock_db = mocker.MagicMock()
    mock_workflow = mocker.MagicMock(spec=Workflow)
    mock_db.get.return_value = mock_workflow    
    result = get_workflow_from_db(mock_db, 123)
    
    mock_db.get.assert_called_once_with(Workflow, 123)
    assert result == mock_workflow

def test_delete_workflow_from_db(mocker):
    """Test delete_workflow_from_db."""
    mock_db = mocker.MagicMock()
    mock_workflow = mocker.MagicMock(spec=Workflow)
    mock_db.get.return_value = mock_workflow
    
    delete_workflow_from_db(mock_db, 123)
    
    mock_db.get.assert_called_once_with(Workflow, 123)
    mock_db.delete.assert_called_once_with(mock_workflow)
    mock_db.commit.assert_called_once()

def test_get_file_workflows_from_db(mocker):
    """Test get_file_workflows_from_db."""
    mock_get_file = mocker.patch("datastores.sql.crud.workflow.get_file_from_db")
    mock_db = mocker.MagicMock()
    mock_file = mocker.MagicMock()
    mock_file.workflows = ["workflow1", "workflow2"]
    mock_get_file.return_value = mock_file
    
    result = get_file_workflows_from_db(mock_db, 1)
    
    mock_get_file.assert_called_once_with(mock_db, 1)
    assert result == ["workflow1", "workflow2"]

def test_get_folder_workflows_from_db(mocker):
    """Test get_folder_workflows_from_db."""
    mock_db = mocker.MagicMock()
    mock_query = mock_db.query.return_value
    mock_filter = mock_query.filter_by.return_value
    mock_order = mock_filter.order_by.return_value
    mock_order.all.return_value = ["workflow1"]
    
    result = get_folder_workflows_from_db(mock_db, 1)
    
    mock_db.query.assert_called_once_with(Workflow)
    mock_query.filter_by.assert_called_once_with(folder_id=1)
    assert result == ["workflow1"]

def test_create_workflow_in_db(mocker):
    """Test create_workflow_in_db."""
    mock_get_file = mocker.patch("datastores.sql.crud.workflow.get_file_from_db")
    mock_uuid = mocker.patch("datastores.sql.crud.workflow.uuid")
    
    mock_db = mocker.MagicMock()
    mock_workflow_schema = mocker.MagicMock()
    mock_workflow_schema.display_name = "test"
    mock_workflow_schema.description = "desc"
    mock_workflow_schema.spec_json = "{}"
    mock_workflow_schema.file_ids = [1]
    mock_workflow_schema.folder_id = 1
    mock_workflow_schema.template_id = 1
    mock_workflow_schema.user_id = 1
    
    mock_file = mocker.MagicMock()
    mock_get_file.return_value = mock_file
    mock_uuid.uuid4.return_value = "mocked_uuid"
    
    result = create_workflow_in_db(mock_db, mock_workflow_schema)
    
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()
    mock_db.refresh.assert_called_once()
    assert result is not None

def test_update_workflow_in_db(mocker):
    """Test update_workflow_in_db."""
    mock_get_workflow = mocker.patch("datastores.sql.crud.workflow.get_workflow_from_db")
    mock_db = mocker.MagicMock()
    mock_workflow_in_db = mocker.MagicMock()
    mock_get_workflow.return_value = mock_workflow_in_db
    
    mock_workflow_schema = mocker.MagicMock()
    mock_workflow_schema.model_dump.return_value = {"display_name": "new_name"}
    
    result = update_workflow_in_db(mock_db, mock_workflow_schema)
    
    mock_get_workflow.assert_called_once()
    mock_db.commit.assert_called_once()
    assert result == mock_workflow_in_db

def test_delete_workflow_template_from_db(mocker):
    """Test delete_workflow_template_from_db."""
    mock_db = mocker.MagicMock()
    mock_template = mocker.MagicMock()
    mock_db.get.return_value = mock_template
    
    delete_workflow_template_from_db(mock_db, 1)
    
    mock_db.get.assert_called_once_with(WorkflowTemplate, 1)
    mock_db.delete.assert_called_once_with(mock_template)
    mock_db.commit.assert_called_once()

def test_delete_workflow_template_from_db_not_found(mocker):
    """Test delete_workflow_template_from_db raising ValueError."""
    mock_db = mocker.MagicMock()
    mock_db.get.return_value = None
    
    with pytest.raises(ValueError):
        delete_workflow_template_from_db(mock_db, 1)

def test_get_workflow_template_from_db(mocker):
    """Test get_workflow_template_from_db."""
    mock_db = mocker.MagicMock()
    mock_template = mocker.MagicMock()
    mock_db.get.return_value = mock_template
    
    result = get_workflow_template_from_db(mock_db, 1)
    
    mock_db.get.assert_called_once_with(WorkflowTemplate, 1)
    assert result == mock_template

def test_create_workflow_template_in_db(mocker):
    """Test create_workflow_template_in_db."""
    mock_db = mocker.MagicMock()
    mock_template_schema = mocker.MagicMock()
    mock_template_schema.display_name = "test"
    mock_template_schema.spec_json = "{}"
    mock_template_schema.user_id = 1
    
    result = create_workflow_template_in_db(mock_db, mock_template_schema)
    
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()
    mock_db.refresh.assert_called_once()
    assert result is not None

def test_update_workflow_template_in_db(mocker):
    """Test update_workflow_template_in_db."""
    mock_db = mocker.MagicMock()
    mock_template_in_db = mocker.MagicMock()
    mock_db.get.return_value = mock_template_in_db
    
    mock_template_schema = mocker.MagicMock()
    mock_template_schema.model_dump.return_value = {"display_name": "new_name"}
    
    result = update_workflow_template_in_db(mock_db, mock_template_schema)
    
    mock_db.get.assert_called_once()
    mock_db.commit.assert_called_once()
    assert result == mock_template_in_db

def test_get_task_from_db(mocker):
    """Test get_task_from_db."""
    mock_db = mocker.MagicMock()
    mock_task = mocker.MagicMock(spec=Task)
    mock_db.get.return_value = mock_task
    
    result = get_task_from_db(mock_db, "task_id")
    
    mock_db.get.assert_called_once_with(Task, "task_id")
    assert result == mock_task

def test_get_task_by_uuid_from_db(mocker):
    """Test get_task_by_uuid_from_db."""
    mock_db = mocker.MagicMock()
    mock_query = mock_db.query.return_value
    mock_filter = mock_query.filter_by.return_value
    mock_filter.first.return_value = "mock_task"
    
    my_uuid = str(uuid.uuid4())
    result = get_task_by_uuid_from_db(mock_db, my_uuid)
    
    mock_db.query.assert_called_once_with(Task)
    mock_query.filter_by.assert_called_once_with(uuid=uuid.UUID(my_uuid))
    assert result == "mock_task"

def test_create_task_in_db(mocker):
    """Test create_task_in_db."""
    mock_db = mocker.MagicMock()
    mock_task = mocker.MagicMock()
    
    result = create_task_in_db(mock_db, mock_task)
    
    mock_db.add.assert_called_once_with(mock_task)
    mock_db.commit.assert_called_once()
    mock_db.refresh.assert_called_once_with(mock_task)
    assert result == mock_task

def test_create_task_report_in_db(mocker):
    """Test create_task_report_in_db."""
    mock_db = mocker.MagicMock()
    mock_report_schema = mocker.MagicMock()
    mock_report_schema.summary = "sum"
    mock_report_schema.priority = "P0"
    mock_report_schema.markdown = "md"
    
    result = create_task_report_in_db(mock_db, mock_report_schema, 1)
    
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()
    mock_db.refresh.assert_called_once()
    assert result is not None

def test_get_workflow_templates_from_db(mocker):
    """Test get_workflow_templates_from_db."""
    mock_add_unique_params = mocker.patch("datastores.sql.crud.workflow.workflow_utils.add_unique_parameter_names")
    mock_db = mocker.MagicMock()
    
    # Template 1: No task_config
    temp1 = mocker.MagicMock(spec=WorkflowTemplate)
    temp1.spec_json = "{}"
    
    # Template 2: Has task_config, no param_name
    temp2 = mocker.MagicMock(spec=WorkflowTemplate)
    temp2.spec_json = '{"task_config": []}'
    
    # Template 3: Has both (should skip update)
    temp3 = mocker.MagicMock(spec=WorkflowTemplate)
    temp3.spec_json = '{"task_config": [], "param_name": "foo"}'
    
    # Template 4: Invalid JSON
    temp4 = mocker.MagicMock(spec=WorkflowTemplate)

    temp4.spec_json = '{"task_config": invalid}'
    
    mock_query = mock_db.query.return_value
    mock_order = mock_query.order_by.return_value
    mock_order.all.return_value = [temp1, temp2, temp3, temp4]
    
    result = get_workflow_templates_from_db(mock_db)
    
    assert len(result) == 4
    # temp2 should be updated
    mock_add_unique_params.assert_called_once()
    mock_db.add.assert_called_once_with(temp2)
    mock_db.commit.assert_called_once()

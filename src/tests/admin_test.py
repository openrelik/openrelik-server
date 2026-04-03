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

"""Tests for admin CLI commands."""

import pytest
import typer
from datetime import timedelta
from typer.testing import CliRunner
from admin import app, parse_retention_time
runner = CliRunner()

def test_create_user_success(mocker):
    """Test create_user command success."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mock_get_user = mocker.patch("admin.get_user_by_username_from_db")
    mock_get_user.return_value = None
    
    mock_create_user_db = mocker.patch("admin.create_user_in_db")
    
    result = runner.invoke(app, ["create-user", "testuser", "-p", "password"])
    
    assert result.exit_code == 0
    assert "User with username 'testuser' created" in result.stdout
    mock_create_user_db.assert_called_once()

def test_create_user_already_exists(mocker):
    """Test create_user command when user already exists."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mock_get_user = mocker.patch("admin.get_user_by_username_from_db")
    mock_get_user.return_value = mocker.MagicMock() # User exists
    
    result = runner.invoke(app, ["create-user", "testuser", "-p", "password"])
    
    assert result.exit_code == 1
    assert "Error: User already exists." in result.stdout


def test_change_password_success(mocker):
    """Test change_password command success."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mock_user = mocker.MagicMock()
    mock_user.auth_method = "local"
    mocker.patch("admin.get_user_by_username_from_db", return_value=mock_user)
    mock_hasher = mocker.MagicMock()
    mock_hasher.hash.return_value = "hashed_password"
    mocker.patch("admin.password_hasher", mock_hasher)
    
    result = runner.invoke(app, ["change-password", "testuser", "-p", "newpassword"])
    
    assert result.exit_code == 0
    assert "Password updated for user 'testuser'" in result.stdout
    assert mock_user.password_hash == "hashed_password"
    mock_db.add.assert_called_once_with(mock_user)
    mock_db.commit.assert_called_once()

def test_change_password_user_not_found(mocker):
    """Test change_password command when user is not found."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mocker.patch("admin.get_user_by_username_from_db", return_value=None)
    
    result = runner.invoke(app, ["change-password", "testuser", "-p", "newpassword"])
    
    assert result.exit_code == 1
    assert "Error: User does not exist." in result.stdout

def test_change_password_not_local(mocker):
    """Test change_password command when user is not local."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mock_user = mocker.MagicMock()
    mock_user.auth_method = "google"
    mocker.patch("admin.get_user_by_username_from_db", return_value=mock_user)
    
    result = runner.invoke(app, ["change-password", "testuser", "-p", "newpassword"])
    
    assert result.exit_code == 1
    assert "Error: You can only change password for local users." in result.stdout

def test_create_api_key_success(mocker):
    """Test create_api_key command success."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mock_user = mocker.MagicMock()
    mock_user.id = 1
    mock_user.uuid.hex = "user_uuid_hex"
    mocker.patch("admin.get_user_by_username_from_db", return_value=mock_user)
    
    mocker.patch("admin.get_config", return_value={"auth": {"jwt_header_default_refresh_expire_minutes": 60}})
    mocker.patch("admin.create_jwt_token", return_value="fake_refresh_token")
    mocker.patch("admin.validate_jwt_token", return_value={"jti": "fake_jti", "exp": 1234567890})
    mock_create_api_key_db = mocker.patch("admin.create_user_api_key_in_db")
    
    result = runner.invoke(app, ["create-api-key", "testuser", "-n", "mykey"])
    
    assert result.exit_code == 0
    assert "fake_refresh_token" in result.stdout
    mock_create_api_key_db.assert_called_once()

def test_create_api_key_user_not_found(mocker):
    """Test create_api_key command when user is not found."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mocker.patch("admin.get_user_by_username_from_db", return_value=None)
    
    result = runner.invoke(app, ["create-api-key", "testuser", "-n", "mykey"])
    
    assert result.exit_code == 1
    assert "Error: User with username 'testuser' not found." in result.stdout

def test_set_admin_true(mocker):
    """Test set_admin command setting admin to True."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mock_user = mocker.MagicMock()
    mocker.patch("admin.get_user_by_username_from_db", return_value=mock_user)
    
    result = runner.invoke(app, ["set-admin", "testuser", "--admin"])
    
    assert result.exit_code == 0
    assert "'testuser' is now an admin." in result.stdout
    assert mock_user.is_admin is True
    mock_db.add.assert_called_once_with(mock_user)
    mock_db.commit.assert_called_once()

def test_set_admin_false(mocker):
    """Test set_admin command setting admin to False."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mock_user = mocker.MagicMock()
    mocker.patch("admin.get_user_by_username_from_db", return_value=mock_user)
    
    result = runner.invoke(app, ["set-admin", "testuser", "--no-admin"])
    
    assert result.exit_code == 0
    assert "Admin privileges removed for 'testuser'." in result.stdout
    assert mock_user.is_admin is False
    mock_db.add.assert_called_once_with(mock_user)
    mock_db.commit.assert_called_once()

def test_set_admin_user_not_found(mocker):
    """Test set_admin command when user is not found."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mocker.patch("admin.get_user_by_username_from_db", return_value=None)
    
    result = runner.invoke(app, ["set-admin", "testuser"])
    
    assert result.exit_code == 1
    assert "Error: User with username 'testuser' not found." in result.stdout

def test_user_details_success(mocker):
    """Test user_details command success."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mock_user = mocker.MagicMock()
    mock_user.username = "testuser"
    mock_user.display_name = "Test User"
    mock_user.uuid = "fake_uuid"
    mock_user.auth_method = "local"
    mock_user.is_admin = False
    mocker.patch("admin.get_user_by_username_from_db", return_value=mock_user)
    
    result = runner.invoke(app, ["user-details", "testuser"])
    
    assert result.exit_code == 0
    assert "User Details: testuser" in result.stdout
    assert "testuser" in result.stdout
    assert "Test User" in result.stdout

def test_user_details_user_not_found(mocker):
    """Test user_details command when user is not found."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mocker.patch("admin.get_user_by_username_from_db", return_value=None)
    
    result = runner.invoke(app, ["user-details", "testuser"])
    
    assert result.exit_code == 1
    assert "Error: User with username 'testuser' not found." in result.stdout

def test_list_users(mocker):
    """Test list_users command."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mock_user1 = mocker.MagicMock()
    mock_user1.username = "user1"
    mock_user1.display_name = "User One"
    mock_user1.uuid = "uuid1"
    mock_user1.is_admin = True
    mock_user1.is_active = True
    mock_user1.is_robot = False
    mock_user1.created_at = "2026-04-03"
    
    mock_user2 = mocker.MagicMock()
    mock_user2.username = "user2"
    mock_user2.display_name = "User Two"
    mock_user2.uuid = "uuid2"
    mock_user2.is_admin = False
    mock_user2.is_active = True
    mock_user2.is_robot = True
    mock_user2.created_at = "2026-04-03"
    
    mocker.patch("admin.get_users_from_db", return_value=[mock_user1, mock_user2])
    
    result = runner.invoke(app, ["list-users"])
    
    assert result.exit_code == 0
    assert "List of Users" in result.stdout
    assert "user1" in result.stdout
    assert "user2" in result.stdout

def test_fix_ownership(mocker):
    """Test fix_ownership command."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mock_file = mocker.MagicMock()
    mock_file.user = mocker.MagicMock()
    mock_file.user_roles = []
    
    mock_folder = mocker.MagicMock()
    mock_folder.user = mocker.MagicMock()
    mock_folder.user_roles = []
    
    mock_query_file = mocker.MagicMock()
    mock_query_file.filter.return_value.all.return_value = [mock_file]
    
    mock_query_folder = mocker.MagicMock()
    mock_query_folder.filter.return_value.all.return_value = [mock_folder]
    
    mock_db.query.side_effect = [mock_query_file, mock_query_folder]
    
    # Mock UserRole creation
    mock_user_role = mocker.patch("admin.UserRole")
    mock_user_role_instance = mocker.MagicMock()
    mock_user_role.return_value = mock_user_role_instance
    
    result = runner.invoke(app, ["fix-ownership"])
    
    assert result.exit_code == 0
    assert "Added missing OWNER roles to 1 files and 1 folders." in result.stdout
    mock_db.commit.assert_called_once()
    assert len(mock_file.user_roles) == 1
    assert len(mock_folder.user_roles) == 1

def test_list_workflow_templates(mocker):
    """Test list_workflow_templates command."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mock_template = mocker.MagicMock()
    mock_template.id = 1
    mock_template.display_name = "Template One"
    mock_template.description = "Description One"
    mock_template.spec_json = "{}"
    mock_template.user.username = "testuser"
    
    mocker.patch("admin.get_workflow_templates_from_db", return_value=[mock_template])
    
    result = runner.invoke(app, ["list-workflow-templates"])
    
    assert result.exit_code == 0
    assert "List of Workflow Templates" in result.stdout
    assert "Template One" in result.stdout
    assert "testuser" in result.stdout

def test_purge_deleted_files_success(mocker):
    """Test purge_deleted_files command success."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value = mock_db
    
    mocker.patch("admin.get_config", return_value={"server": {"storage_path": "/tmp/storage"}})
    
    # Mock summary query result
    mock_summary_res = mocker.MagicMock()
    mock_summary_res.first.return_value = (1, 1024) # 1 file, 1024 bytes
    
    # Mock streaming query result
    mock_partition = [(1, mocker.MagicMock(hex="file_uuid"), "txt", 10)] # file_id, uuid, ext, folder_id
    
    mock_execute = mocker.MagicMock()
    mock_db.execute = mock_execute
    mock_execute.side_effect = [
        mock_summary_res, # 1. Summary
        mocker.MagicMock(partitions=mocker.MagicMock(return_value=[mock_partition])), # 2. Streaming files
        mocker.MagicMock(all=mocker.MagicMock(return_value=[(10, mocker.MagicMock(hex="folder_uuid"))])), # 3. Folder components
        mocker.MagicMock() # 4. Update query
    ]
    
    # Mock confirm
    mocker.patch("typer.confirm", return_value=True)
    
    mocker.patch("os.path.exists", return_value=True)
    mock_remove = mocker.patch("os.remove")
    
    result = runner.invoke(app, ["purge-deleted-files"])
    
    assert result.exit_code == 0
    assert "Successfully purged 1 files" in result.stdout
    mock_remove.assert_called_once()
    mock_db.commit.assert_called_once()

def test_purge_deleted_files_no_files(mocker):
    """Test purge_deleted_files command when no files match."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value = mock_db
    
    mocker.patch("admin.get_config", return_value={"server": {"storage_path": "/tmp/storage"}})
    
    mock_summary_res = mocker.MagicMock()
    mock_summary_res.first.return_value = (0, 0)
    mock_db.execute.return_value = mock_summary_res
    
    result = runner.invoke(app, ["purge-deleted-files"])
    
    assert result.exit_code == 0
    assert "No files matching criteria are waiting for purging." in result.stdout

def test_delete_workflow_template_success(mocker):
    """Test delete_workflow_template command success."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mocker.patch("admin.delete_workflow_template_from_db")
    
    result = runner.invoke(app, ["delete-workflow-template", "1"])
    
    assert result.exit_code == 0
    assert "Workflow template with ID 1 has been deleted." in result.stdout

def test_delete_workflow_template_not_found(mocker):
    """Test delete_workflow_template command when template not found."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mocker.patch("admin.delete_workflow_template_from_db", side_effect=ValueError("Workflow template with ID 1 not found."))
    
    result = runner.invoke(app, ["delete-workflow-template", "1"])
    
    assert result.exit_code == 0
    assert "Error: Workflow template with ID 1 not found." in result.stdout


def test_list_groups(mocker):
    """Test list_groups command."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mock_group = mocker.MagicMock()
    mock_group.name = "testgroup"
    mock_group.description = "Test Group"
    mock_group.users = []
    mock_group.created_at = "2026-04-03"
    
    mocker.patch("admin.get_groups_from_db", return_value=[mock_group])
    
    result = runner.invoke(app, ["list-groups"])
    
    assert result.exit_code == 0
    assert "List of Groups" in result.stdout
    assert "testgroup" in result.stdout

def test_create_group_success(mocker):
    """Test create_group command success."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mocker.patch("admin.get_group_by_name_from_db", return_value=None)
    mock_create = mocker.patch("admin.create_group_in_db")
    
    result = runner.invoke(app, ["create-group", "newgroup", "--description", "New Group"])
    
    assert result.exit_code == 0
    assert "Group 'newgroup' created" in result.stdout
    mock_create.assert_called_once()

def test_create_group_already_exists(mocker):
    """Test create_group command when group already exists."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mocker.patch("admin.get_group_by_name_from_db", return_value=mocker.MagicMock())
    
    result = runner.invoke(app, ["create-group", "existinggroup"])
    
    assert result.exit_code == 1
    assert "Group 'existinggroup' already exists." in result.stdout

def test_rename_group_success(mocker):
    """Test rename_group command success."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mock_group = mocker.MagicMock()
    mock_group.name = "oldgroup"
    
    mocker.patch("admin.get_group_by_name_from_db", return_value=mock_group)
    
    result = runner.invoke(app, ["rename-group", "oldgroup", "newgroup"])
    
    assert result.exit_code == 0
    assert "Group 'oldgroup' renamed to 'newgroup'." in result.stdout
    assert mock_group.name == "newgroup"
    mock_db.commit.assert_called_once()

def test_rename_group_not_found(mocker):
    """Test rename_group command when group not found."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mocker.patch("admin.get_group_by_name_from_db", return_value=None)
    
    result = runner.invoke(app, ["rename-group", "nonexistentgroup", "newgroup"])
    
    assert result.exit_code == 1
    assert "Group 'nonexistentgroup' not found." in result.stdout

def test_add_users_to_group_success(mocker):
    """Test add_users_to_group command success."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mock_group = mocker.MagicMock()
    mock_group.users = []
    
    mocker.patch("admin.get_group_by_name_from_db", return_value=mock_group)
    
    mock_user = mocker.MagicMock()
    mocker.patch("admin.get_user_by_username_from_db", return_value=mock_user)
    
    result = runner.invoke(app, ["add-users-to-group", "testgroup", "user1"])
    
    assert result.exit_code == 0
    assert "User 'user1' added to group 'testgroup'." in result.stdout
    assert mock_user in mock_group.users
    mock_db.commit.assert_called_once()

def test_remove_users_from_group_success(mocker):
    """Test remove_users_from_group command success."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mock_group = mocker.MagicMock()
    mock_user = mocker.MagicMock()
    mock_group.users = [mock_user]
    
    mocker.patch("admin.get_group_by_name_from_db", return_value=mock_group)
    mocker.patch("admin.get_user_by_username_from_db", return_value=mock_user)
    mock_remove = mocker.patch("admin.remove_users_from_group_db")
    
    result = runner.invoke(app, ["remove-users-from-group", "testgroup", "user1"])
    
    assert result.exit_code == 0
    assert "Attempted to remove users from group 'testgroup'." in result.stdout
    mock_remove.assert_called_once()

def test_list_group_members_success(mocker):
    """Test list_group_members command success."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mock_group = mocker.MagicMock()
    mock_user = mocker.MagicMock()
    mock_user.username = "user1"
    mock_user.display_name = "User One"
    mock_user.uuid = "uuid1"
    mock_group.users = [mock_user]
    
    mocker.patch("admin.get_group_by_name_from_db", return_value=mock_group)
    
    result = runner.invoke(app, ["list-group-members", "testgroup"])
    
    assert result.exit_code == 0
    assert "Members of Group: testgroup" in result.stdout
    assert "user1" in result.stdout

def test_soft_delete_empty_folders_success(mocker):
    """Test soft_delete_empty_folders command success."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mocker.patch("admin.get_config", return_value={"server": {"storage_path": "/tmp/storage"}})
    
    mock_folder = mocker.MagicMock()
    mock_folder.id = 1
    mock_folder.display_name = "Empty Folder"
    
    mock_execute_res = mocker.MagicMock()
    mock_execute_res.scalars.return_value.all.return_value = [mock_folder]
    mock_db.execute.return_value = mock_execute_res
    
    mocker.patch("typer.confirm", return_value=True)
    
    result = runner.invoke(app, ["soft-delete-empty-folders"])
    
    assert result.exit_code == 0
    assert "Successfully marked 1 empty folders as deleted." in result.stdout
    mock_folder.soft_delete.assert_called_once()
    mock_db.commit.assert_called_once()

def test_soft_delete_empty_folders_dry_run(mocker):
    """Test soft_delete_empty_folders command dry run."""
    mock_session_local = mocker.patch("admin.database.SessionLocal")
    mock_db = mocker.MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mocker.patch("admin.get_config", return_value={"server": {"storage_path": "/tmp/storage"}})
    
    mock_folder = mocker.MagicMock()
    mock_folder.id = 1
    mock_folder.display_name = "Empty Folder"
    
    mock_execute_res = mocker.MagicMock()
    mock_execute_res.scalars.return_value.all.return_value = [mock_folder]
    mock_db.execute.return_value = mock_execute_res
    
    result = runner.invoke(app, ["soft-delete-empty-folders", "--dry-run"])
    
    assert result.exit_code == 0
    assert "Dry run mode enabled" in result.stdout
    assert "Empty Folder" in result.stdout
    mock_folder.soft_delete.assert_not_called()
    mock_db.commit.assert_not_called()

def test_parse_retention_time():
    """Test parse_retention_time function."""
    assert parse_retention_time("10m") == timedelta(minutes=10)
    assert parse_retention_time("5h") == timedelta(hours=5)
    assert parse_retention_time("2D") == timedelta(days=2)
    assert parse_retention_time("1W") == timedelta(weeks=1)
    assert parse_retention_time("3M") == timedelta(days=90)
    assert parse_retention_time("1Y") == timedelta(days=365)
    
    with pytest.raises(typer.BadParameter):
        parse_retention_time("invalid")
    with pytest.raises(typer.BadParameter):
        parse_retention_time("10X")

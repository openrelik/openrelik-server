import unittest

from unittest import mock
from fastapi.testclient import TestClient

from api.v1.taskqueue import router as taskqueue_router
from fastapi import FastAPI


class TestTaskQueue(unittest.TestCase):
    """Tests taskqueue endpoints."""

    def setUp(self):
        self.app = FastAPI()  # Use the app instance
        self.app.include_router(taskqueue_router, prefix="/taskqueue",
                                tags=["taskqueue"], dependencies=[])
        # self.app.dependency_overrides[common_auth.get_current_active_user] = mock.MagicMock(
        #    return_value=mock_user)
        self.client = TestClient(self.app)

    def tearDown(self):
        pass

    @mock.patch("lib.celery_utils.get_registered_tasks")
    def test_get_registered_tasks(self, mock_get_registered_tasks):
        mock_get_registered_tasks.return_value = {"mock_task": "mock_details"}
        response = self.client.get("/taskqueue/tasks/registered")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"mock_task": "mock_details"})

    @mock.patch("lib.celery_utils.get_worker_stats")
    def test_get_worker_stats(self, mock_get_worker_stats):
        mock_get_worker_stats.return_value = {"worker1": {"status": "active"}}
        response = self.client.get("/taskqueue/workers/stats/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"worker1": {"status": "active"}})

    @mock.patch("lib.celery_utils.get_worker_configurations")
    def test_get_worker_configs(self, mock_get_worker_configs):
        mock_get_worker_configs.return_value = {"worker_config_key": "value"}
        response = self.client.get("/taskqueue/workers/configurations/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"worker_config_key": "value"})

    @mock.patch("lib.celery_utils.get_worker_reports")
    def test_get_worker_reports(self, mock_get_worker_reports):
        mock_get_worker_reports.return_value = {
            "worker_id": {"report_key": "report_value"}
        }
        response = self.client.get("/taskqueue/workers/reports/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"worker_id": {
                         "report_key": "report_value"}})

    @mock.patch("lib.celery_utils.ping_workers")
    def test_ping_workers(self, mock_ping_workers):
        mock_ping_workers.return_value = ["pong_worker1", "pong_worker2"]
        response = self.client.get("/taskqueue/workers/ping/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), ["pong_worker1", "pong_worker2"])

    @mock.patch("lib.celery_utils.get_active_tasks")
    def test_get_active_tasks(self, mock_get_active_tasks):
        mock_get_active_tasks.return_value = {"worker1": [{"task_id": "123"}]}
        response = self.client.get("/taskqueue/tasks/active/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"worker1": [{"task_id": "123"}]})

    @mock.patch("lib.celery_utils.get_scheduled_tasks")
    def test_get_scheduled_tasks(self, mock_get_scheduled_tasks):
        mock_get_scheduled_tasks.return_value = [
            {"task_id": "456", "eta": "time"}]
        response = self.client.get("/taskqueue/tasks/scheduled/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [{"task_id": "456", "eta": "time"}])

    @mock.patch("lib.celery_utils.get_reserved_tasks")
    def test_get_reserved_tasks(self, mock_get_reserved_tasks):
        mock_get_reserved_tasks.return_value = {
            "worker1": [{"task_id": "789"}]}
        response = self.client.get("/taskqueue/tasks/reserved/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"worker1": [{"task_id": "789"}]})

    @mock.patch("lib.celery_utils.get_revoked_tasks")
    def test_get_revoked_tasks(self, mock_get_revoked_tasks):
        mock_get_revoked_tasks.return_value = [
            {"task_id": "abc", "reason": "revoked"}
        ]
        response = self.client.get("/taskqueue/tasks/revoked/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [
                         {"task_id": "abc", "reason": "revoked"}])

    @mock.patch("lib.celery_utils.get_active_queues")
    def test_get_active_queues(self, mock_get_active_queues):
        mock_get_active_queues.return_value = [{"name": "queue1"}]
        response = self.client.get("/taskqueue/queues/active/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [{"name": "queue1"}])

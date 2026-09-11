"""Unit tests for Google Tasks integration module."""

from unittest.mock import MagicMock, patch

import pytest

from google_tasks import (
    GOOGLE_TASKS_SCOPE,
    SCOPES,
    complete_google_task,
    create_google_task,
    format_task_due_date,
    get_tasks_service,
    list_google_tasks,
)


def test_google_tasks_scope():
    """Verify that Google Tasks scope is defined correctly."""
    assert GOOGLE_TASKS_SCOPE == "https://www.googleapis.com/auth/tasks"
    assert GOOGLE_TASKS_SCOPE in SCOPES


def test_format_task_due_date():
    """Verify formatting of task due dates to RFC 3339."""
    assert format_task_due_date("") == ""

    # Pure date
    res = format_task_due_date("2026-09-15")
    assert res == "2026-09-15T00:00:00.000Z"

    # Date with time
    res_time = format_task_due_date("2026-09-15 17:30")
    assert "2026-09-15" in res_time
    assert res_time.endswith("Z")


def test_get_tasks_service_unauthenticated():
    """Verify RuntimeError when user is not authenticated."""
    with patch("google_tasks.get_credentials", return_value=None), pytest.raises(
        RuntimeError, match="not authenticated"
    ):
        get_tasks_service()


def test_get_tasks_service_authenticated():
    """Verify build is called with tasks v1 when authenticated."""
    mock_creds = MagicMock()
    mock_creds.valid = True

    with (
        patch("google_tasks.get_credentials", return_value=mock_creds),
        patch("google_tasks.build") as mock_build,
    ):
        get_tasks_service()
        mock_build.assert_called_once_with("tasks", "v1", credentials=mock_creds, cache_discovery=False)


def test_create_google_task_success():
    """Verify create_google_task calls insert with expected parameters."""
    mock_service = MagicMock()
    mock_tasks = MagicMock()
    mock_insert = MagicMock()

    mock_service.tasks.return_value = mock_tasks
    mock_tasks.insert.return_value = mock_insert
    mock_insert.execute.return_value = {
        "id": "task-101",
        "title": "Buy milk",
        "due": "2026-09-15T00:00:00.000Z",
    }

    result = create_google_task(
        title="Buy milk",
        due_date="2026-09-15",
        service=mock_service,
    )

    assert result["id"] == "task-101"
    assert result["title"] == "Buy milk"

    mock_tasks.insert.assert_called_once_with(
        tasklist="@default",
        body={"title": "Buy milk", "due": "2026-09-15T00:00:00.000Z"},
    )


def test_create_google_task_empty_title():
    """Verify ValueError is raised if title is empty."""
    with pytest.raises(ValueError, match="title is required"):
        create_google_task(title="")


def test_list_google_tasks_success():
    """Verify list_google_tasks queries Tasks API with expected defaults."""
    mock_service = MagicMock()
    mock_tasks = MagicMock()
    mock_list = MagicMock()

    mock_service.tasks.return_value = mock_tasks
    mock_tasks.list.return_value = mock_list
    mock_list.execute.return_value = {
        "items": [
            {"id": "t1", "title": "Review PR", "due": "2026-09-16T00:00:00.000Z"},
            {"id": "t2", "title": "Buy milk"},
        ]
    }

    result = list_google_tasks(service=mock_service)
    assert len(result) == 2
    assert result[0]["title"] == "Review PR"
    assert result[1]["title"] == "Buy milk"

    mock_tasks.list.assert_called_once_with(
        tasklist="@default",
        maxResults=20,
        showCompleted=False,
    )


def test_list_google_tasks_empty():
    """Verify list_google_tasks returns empty list when no items returned."""
    mock_service = MagicMock()
    mock_tasks = MagicMock()
    mock_list = MagicMock()

    mock_service.tasks.return_value = mock_tasks
    mock_tasks.list.return_value = mock_list
    mock_list.execute.return_value = {}

    result = list_google_tasks(service=mock_service)
    assert result == []


def test_complete_google_task_success():
    """Verify complete_google_task calls patch with status completed."""
    mock_service = MagicMock()
    mock_tasks = MagicMock()
    mock_patch = MagicMock()

    mock_service.tasks.return_value = mock_tasks
    mock_tasks.patch.return_value = mock_patch
    mock_patch.execute.return_value = {
        "id": "t1",
        "title": "Buy groceries",
        "status": "completed",
    }

    result = complete_google_task(task_id="t1", service=mock_service)
    assert result["id"] == "t1"
    assert result["status"] == "completed"

    mock_tasks.patch.assert_called_once_with(
        tasklist="@default",
        task="t1",
        body={"status": "completed"},
    )


def test_complete_google_task_empty_id():
    """Verify ValueError is raised if task_id is empty."""
    with pytest.raises(ValueError, match="Task ID is required"):
        complete_google_task(task_id="")

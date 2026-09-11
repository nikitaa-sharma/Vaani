"""Google Tasks integration module for Vaani.

Provides integration with the Google Tasks API using the existing backend
Google OAuth credentials and the Google Tasks scope.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from googleapiclient.discovery import Resource, build

try:
    from google_calendar_auth import get_credentials
except ImportError:
    from src.google_calendar_auth import get_credentials

logger = logging.getLogger("google_tasks")

# Scope for Google Tasks API
GOOGLE_TASKS_SCOPE = "https://www.googleapis.com/auth/tasks"
SCOPES = [GOOGLE_TASKS_SCOPE]


def format_task_due_date(due_str: str) -> str:
    """Parse and format date string into RFC 3339 timestamp required by Google Tasks API.

    Google Tasks requires RFC 3339 timestamps (e.g., 'YYYY-MM-DDTHH:MM:SS.000Z').

    Args:
        due_str: Input date string in standard formats (e.g., '2026-09-15', '2026-09-15 17:00').

    Returns:
        Formatted RFC 3339 string.
    """
    cleaned = due_str.strip()
    if not cleaned:
        return ""

    # Pure date format YYYY-MM-DD
    if len(cleaned) == 10 and cleaned.count("-") == 2 and ":" not in cleaned:
        return f"{cleaned}T00:00:00.000Z"

    normalized = cleaned.replace(" ", "T")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in (
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %I:%M %p",
            "%Y/%m/%d %H:%M",
            "%Y/%m/%d",
            "%d-%m-%Y %H:%M",
            "%d-%m-%Y",
        ):
            try:
                dt = datetime.strptime(cleaned, fmt)
                break
            except ValueError:
                continue
        else:
            return f"{cleaned}T00:00:00.000Z" if "T" not in cleaned else cleaned

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def get_tasks_service(token_path: Path | str | None = None) -> Resource:
    """Construct an authorized Google Tasks API Resource service.

    Args:
        token_path: Optional custom path to credentials file.

    Returns:
        googleapiclient.discovery.Resource for Google Tasks API v1.

    Raises:
        RuntimeError: If user is not authenticated.
    """
    creds = get_credentials(token_path=token_path, auto_refresh=True)
    if not creds:
        raise RuntimeError(
            "Google account is not authenticated. Complete Google OAuth flow first."
        )

    return build("tasks", "v1", credentials=creds, cache_discovery=False)


def create_google_task(
    title: str,
    due_date: str = "",
    tasklist: str = "@default",
    service: Resource | None = None,
    token_path: Path | str | None = None,
) -> dict[str, Any]:
    """Create a task in the user's Google Tasks.

    Args:
        title: The task title or description.
        due_date: Optional due date/time string.
        tasklist: The tasklist identifier (default is '@default').
        service: Optional pre-constructed Tasks service.
        token_path: Optional path to credentials.

    Returns:
        The created task resource dict from the Google Tasks API.

    Raises:
        ValueError: If title is empty.
        RuntimeError: If not authenticated.
    """
    if not title or not title.strip():
        raise ValueError("Task title is required.")

    if service is None:
        service = get_tasks_service(token_path=token_path)

    body: dict[str, Any] = {"title": title.strip()}
    if due_date and due_date.strip():
        formatted_due = format_task_due_date(due_date)
        if formatted_due:
            body["due"] = formatted_due

    return service.tasks().insert(tasklist=tasklist, body=body).execute()


def list_google_tasks(
    tasklist: str = "@default",
    max_results: int = 20,
    show_completed: bool = False,
    service: Resource | None = None,
    token_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve tasks from the specified Google Tasks list.

    Args:
        tasklist: The tasklist identifier (default is '@default').
        max_results: Maximum number of tasks to return (default 20, max 100).
        show_completed: Whether to include completed tasks (default False).
        service: Optional pre-constructed Tasks service.
        token_path: Optional path to credentials.

    Returns:
        List of task resource dictionaries.

    Raises:
        RuntimeError: If not authenticated.
    """
    if service is None:
        service = get_tasks_service(token_path=token_path)

    results = service.tasks().list(
        tasklist=tasklist,
        maxResults=min(max(1, max_results), 100),
        showCompleted=show_completed,
    ).execute()

    return results.get("items", [])


def complete_google_task(
    task_id: str,
    tasklist: str = "@default",
    service: Resource | None = None,
    token_path: Path | str | None = None,
) -> dict[str, Any]:
    """Mark a task as completed in the user's Google Tasks.

    Args:
        task_id: The unique task identifier.
        tasklist: The tasklist identifier (default is '@default').
        service: Optional pre-constructed Tasks service.
        token_path: Optional path to credentials.

    Returns:
        The updated task resource dict from the Google Tasks API.

    Raises:
        ValueError: If task_id is empty.
        RuntimeError: If not authenticated.
    """
    if not task_id or not task_id.strip():
        raise ValueError("Task ID is required.")

    if service is None:
        service = get_tasks_service(token_path=token_path)

    return (
        service.tasks()
        .patch(tasklist=tasklist, task=task_id.strip(), body={"status": "completed"})
        .execute()
    )

# Agent behavior is covered by the simulations in scenarios.yaml, which run full
# conversations against the agent on LiveKit Cloud (see README.md). The eval
# below is kept as an example of the in-process testing framework
# (https://docs.livekit.io/agents/start/testing/) for turn-level checks that
# don't need a live session. Uncomment it and run `uv run pytest` to use it.
#
# import textwrap
#
# import pytest
# from livekit.agents import AgentSession, inference, llm
#
# from agent import Assistant
#
#
# def _judge_llm() -> llm.LLM:
#     return inference.LLM(model="openai/gpt-4.1-mini")
#
#
# @pytest.mark.asyncio
# async def test_offers_assistance() -> None:
#     """Evaluation of the agent's friendly nature."""
#     async with (
#         _judge_llm() as judge_llm,
#         AgentSession() as session,
#     ):
#         await session.start(Assistant())
#
#         # Run an agent turn following the user's greeting
#         result = await session.run(user_input="Hello")
#
#         # Evaluate the agent's response for friendliness
#         await (
#             result.expect.next_event()
#             .is_message(role="assistant")
#             .judge(
#                 judge_llm,
#                 intent=textwrap.dedent(
#                     """\
#                     Greets the user in a friendly manner.
#
#                     Optional context that may or may not be included:
#                     - Offer of assistance with any request the user may have
#                     - Other small talk or chit chat is acceptable, so long as it is friendly and not too intrusive
#                     """
#                 ),
#             )
#         )
#
#         # Ensures there are no function calls or other unexpected events
#         result.expect.no_more_events()

import pytest


def test_agent_imports():
    """Verify that the agent module imports successfully."""
    import agent

    assert hasattr(agent, "server")
    assert hasattr(agent, "Assistant")
    assert hasattr(agent, "create_calendar_event")
    assert hasattr(agent, "search_calendar_events")
    assert hasattr(agent, "update_calendar_event")
    assert hasattr(agent, "delete_calendar_event")
    assert hasattr(agent, "create_task")
    assert hasattr(agent, "list_tasks")
    assert hasattr(agent, "complete_task")
    assert hasattr(agent, "create_email_draft")
    assert hasattr(agent, "list_email_drafts")
    assert hasattr(agent, "update_email_draft")
    assert hasattr(agent, "delete_email_draft")
    assert hasattr(agent, "send_email")


def test_assistant_registers_create_calendar_event():
    """Verify Assistant registers create_calendar_event among its tools."""
    from agent import Assistant, create_calendar_event

    assistant = Assistant()
    tool_names = [t.name if hasattr(t, "name") else getattr(t, "__name__", str(t)) for t in assistant.tools]
    assert "create_calendar_event" in tool_names or create_calendar_event in assistant.tools


@pytest.mark.asyncio
async def test_create_calendar_event_success():
    """Verify create_calendar_event calls Calendar API and returns confirmation."""
    from unittest.mock import MagicMock, patch

    from agent import create_calendar_event

    mock_service = MagicMock()
    mock_events = MagicMock()
    mock_insert = MagicMock()

    mock_service.events.return_value = mock_events
    mock_events.insert.return_value = mock_insert
    mock_insert.execute.return_value = {
        "id": "event-123",
        "summary": "Doctor Appointment",
        "start": {"dateTime": "2026-09-12T10:00:00+05:30"},
        "end": {"dateTime": "2026-09-12T11:00:00+05:30"},
        "location": "City Clinic",
    }

    mock_context = MagicMock()

    with patch("agent.get_calendar_service", return_value=mock_service):
        response = await create_calendar_event(
            mock_context,
            title="Doctor Appointment",
            start_time="2026-09-12 10:00",
            end_time="2026-09-12 11:00",
            description="Annual checkup",
            location="City Clinic",
        )

        assert "Doctor Appointment" in response
        assert "City Clinic" in response
        assert "successfully scheduled" in response

        mock_events.insert.assert_called_once()
        _, kwargs = mock_events.insert.call_args
        assert kwargs["calendarId"] == "primary"
        body = kwargs["body"]
        assert body["summary"] == "Doctor Appointment"
        assert body["description"] == "Annual checkup"
        assert body["location"] == "City Clinic"
        assert "dateTime" in body["start"]
        assert "dateTime" in body["end"]


@pytest.mark.asyncio
async def test_create_calendar_event_with_attendees_invites():
    """Verify create_calendar_event passes attendees and sendUpdates='all' to Google Calendar."""
    from unittest.mock import MagicMock, patch

    from agent import create_calendar_event

    mock_service = MagicMock()
    mock_events = MagicMock()
    mock_insert = MagicMock()

    mock_service.events.return_value = mock_events
    mock_events.insert.return_value = mock_insert
    mock_insert.execute.return_value = {
        "id": "event-invite-456",
        "summary": "Project Kickoff",
        "start": {"dateTime": "2026-09-14T14:00:00+05:30"},
        "end": {"dateTime": "2026-09-14T15:00:00+05:30"},
        "location": "Boardroom",
    }

    mock_context = MagicMock()

    with patch("agent.get_calendar_service", return_value=mock_service):
        response = await create_calendar_event(
            mock_context,
            title="Project Kickoff",
            start_time="2026-09-14 14:00",
            end_time="2026-09-14 15:00",
            description="Q3 planning",
            location="Boardroom",
            attendees=["colleague@example.com", "client@example.com"],
        )

        assert "Project Kickoff" in response
        assert "successfully scheduled" in response
        assert "colleague@example.com" in response
        assert "client@example.com" in response

        mock_events.insert.assert_called_once()
        _, kwargs = mock_events.insert.call_args
        assert kwargs["calendarId"] == "primary"
        assert kwargs["sendUpdates"] == "all"
        body = kwargs["body"]
        assert body["summary"] == "Project Kickoff"
        assert body["attendees"] == [
            {"email": "colleague@example.com"},
            {"email": "client@example.com"},
        ]


@pytest.mark.asyncio
async def test_create_calendar_event_unauthenticated():
    """Verify create_calendar_event returns clear message when not authenticated."""
    from unittest.mock import MagicMock, patch

    from agent import create_calendar_event

    mock_context = MagicMock()

    with patch("agent.get_calendar_service", side_effect=RuntimeError("Not authenticated")):
        response = await create_calendar_event(
            mock_context,
            title="Team Lunch",
            start_time="2026-09-12 12:00",
            end_time="2026-09-12 13:00",
        )

        assert "not connected" in response or "authenticate" in response.lower()


@pytest.mark.asyncio
async def test_create_calendar_event_missing_fields():
    """Verify validation when required fields are missing."""
    from unittest.mock import MagicMock

    from agent import create_calendar_event

    mock_context = MagicMock()

    res_empty_title = await create_calendar_event(
        mock_context,
        title="",
        start_time="2026-09-12 12:00",
        end_time="2026-09-12 13:00",
    )
    assert "title is required" in res_empty_title.lower()

    res_empty_start = await create_calendar_event(
        mock_context,
        title="Sync",
        start_time="",
        end_time="2026-09-12 13:00",
    )
    assert "start time is required" in res_empty_start.lower()


def test_assistant_registers_search_calendar_events():
    """Verify Assistant registers search_calendar_events among its tools."""
    from agent import Assistant, search_calendar_events

    assistant = Assistant()
    tool_names = [t.name if hasattr(t, "name") else getattr(t, "__name__", str(t)) for t in assistant.tools]
    assert "search_calendar_events" in tool_names or search_calendar_events in assistant.tools


@pytest.mark.asyncio
async def test_search_calendar_events_success():
    """Verify search_calendar_events returns matching events."""
    from unittest.mock import MagicMock, patch

    from agent import search_calendar_events

    mock_service = MagicMock()
    mock_events = MagicMock()
    mock_list = MagicMock()

    mock_service.events.return_value = mock_events
    mock_events.list.return_value = mock_list
    mock_list.execute.return_value = {
        "items": [
            {
                "id": "evt-001",
                "summary": "Dentist Appointment",
                "start": {"dateTime": "2026-09-15T09:00:00+05:30"},
                "end": {"dateTime": "2026-09-15T10:00:00+05:30"},
            },
            {
                "id": "evt-002",
                "summary": "Dentist Follow-up",
                "start": {"dateTime": "2026-09-22T09:00:00+05:30"},
                "end": {"dateTime": "2026-09-22T10:00:00+05:30"},
            },
        ]
    }

    mock_context = MagicMock()

    with patch("agent.get_calendar_service", return_value=mock_service):
        response = await search_calendar_events(
            mock_context,
            query="dentist",
        )

        assert "Found 2 event(s)" in response
        assert "Dentist Appointment" in response
        assert "Dentist Follow-up" in response
        assert "evt-001" in response
        assert "evt-002" in response

        mock_events.list.assert_called_once()
        _, kwargs = mock_events.list.call_args
        assert kwargs["calendarId"] == "primary"
        assert kwargs["q"] == "dentist"
        assert kwargs["singleEvents"] is True


@pytest.mark.asyncio
async def test_search_calendar_events_unauthenticated():
    """Verify search_calendar_events returns clear message when not authenticated."""
    from unittest.mock import MagicMock, patch

    from agent import search_calendar_events

    mock_context = MagicMock()

    with patch("agent.get_calendar_service", side_effect=RuntimeError("Not authenticated")):
        response = await search_calendar_events(
            mock_context,
            query="meeting",
        )

        assert "not connected" in response or "authenticate" in response.lower()


@pytest.mark.asyncio
async def test_search_calendar_events_empty_query():
    """Verify validation when query is empty."""
    from unittest.mock import MagicMock

    from agent import search_calendar_events

    mock_context = MagicMock()

    response = await search_calendar_events(mock_context, query="")
    assert "search query is required" in response.lower()


@pytest.mark.asyncio
async def test_search_calendar_events_no_results():
    """Verify response when no events match the query."""
    from unittest.mock import MagicMock, patch

    from agent import search_calendar_events

    mock_service = MagicMock()
    mock_events = MagicMock()
    mock_list = MagicMock()

    mock_service.events.return_value = mock_events
    mock_events.list.return_value = mock_list
    mock_list.execute.return_value = {"items": []}

    mock_context = MagicMock()

    with patch("agent.get_calendar_service", return_value=mock_service):
        response = await search_calendar_events(
            mock_context,
            query="nonexistent-xyz",
        )

        assert "No events found" in response
        assert "nonexistent-xyz" in response


def test_assistant_registers_update_and_delete_calendar_events():
    """Verify Assistant registers update_calendar_event and delete_calendar_event among its tools."""
    from agent import Assistant, delete_calendar_event, update_calendar_event

    assistant = Assistant()
    tool_names = [t.name if hasattr(t, "name") else getattr(t, "__name__", str(t)) for t in assistant.tools]
    assert "update_calendar_event" in tool_names or update_calendar_event in assistant.tools
    assert "delete_calendar_event" in tool_names or delete_calendar_event in assistant.tools


@pytest.mark.asyncio
async def test_update_calendar_event_success():
    """Verify update_calendar_event patches event and returns confirmation."""
    from unittest.mock import MagicMock, patch

    from agent import update_calendar_event

    mock_service = MagicMock()
    mock_events = MagicMock()
    mock_patch = MagicMock()

    mock_service.events.return_value = mock_events
    mock_events.patch.return_value = mock_patch
    mock_patch.execute.return_value = {
        "id": "evt-123",
        "summary": "Updated Team Sync",
        "start": {"dateTime": "2026-09-15T15:00:00+05:30"},
        "end": {"dateTime": "2026-09-15T16:00:00+05:30"},
    }

    mock_context = MagicMock()

    with patch("agent.get_calendar_service", return_value=mock_service):
        response = await update_calendar_event(
            mock_context,
            event_id="evt-123",
            title="Updated Team Sync",
            start_time="2026-09-15 15:00",
            end_time="2026-09-15 16:00",
        )

        assert "Updated Team Sync" in response
        assert "evt-123" in response
        assert "successfully updated" in response

        mock_events.patch.assert_called_once()
        _, kwargs = mock_events.patch.call_args
        assert kwargs["calendarId"] == "primary"
        assert kwargs["eventId"] == "evt-123"
        body = kwargs["body"]
        assert body["summary"] == "Updated Team Sync"
        assert "dateTime" in body["start"]
        assert "dateTime" in body["end"]


@pytest.mark.asyncio
async def test_update_calendar_event_with_attendees_invites():
    """Verify update_calendar_event includes attendees and sendUpdates='all' in the Calendar API request."""
    from unittest.mock import MagicMock, patch

    from agent import update_calendar_event

    mock_service = MagicMock()
    mock_events = MagicMock()
    mock_patch = MagicMock()

    mock_service.events.return_value = mock_events
    mock_events.patch.return_value = mock_patch
    mock_patch.execute.return_value = {
        "id": "evt-789",
        "summary": "Design Review",
        "start": {"dateTime": "2026-09-16T10:00:00+05:30"},
        "end": {"dateTime": "2026-09-16T11:00:00+05:30"},
    }

    mock_context = MagicMock()

    with patch("agent.get_calendar_service", return_value=mock_service):
        response = await update_calendar_event(
            mock_context,
            event_id="evt-789",
            attendees=["designer@example.com", "product@example.com"],
        )

        assert "Design Review" in response
        assert "evt-789" in response
        assert "successfully updated" in response
        assert "designer@example.com" in response
        assert "product@example.com" in response

        mock_events.patch.assert_called_once()
        _, kwargs = mock_events.patch.call_args
        assert kwargs["calendarId"] == "primary"
        assert kwargs["eventId"] == "evt-789"
        assert kwargs["sendUpdates"] == "all"
        body = kwargs["body"]
        assert body["attendees"] == [
            {"email": "designer@example.com"},
            {"email": "product@example.com"},
        ]


@pytest.mark.asyncio
async def test_update_calendar_event_missing_id():
    """Verify update_calendar_event validation when event_id is empty."""
    from unittest.mock import MagicMock

    from agent import update_calendar_event

    mock_context = MagicMock()
    res = await update_calendar_event(mock_context, event_id="", title="New Title")
    assert "event id is required" in res.lower()


@pytest.mark.asyncio
async def test_update_calendar_event_no_fields():
    """Verify update_calendar_event validation when no update fields are specified."""
    from unittest.mock import MagicMock

    from agent import update_calendar_event

    mock_context = MagicMock()
    res = await update_calendar_event(mock_context, event_id="evt-123")
    assert "specify at least one field to update" in res.lower()


@pytest.mark.asyncio
async def test_update_calendar_event_unauthenticated():
    """Verify update_calendar_event behavior when Google Calendar is not connected."""
    from unittest.mock import MagicMock, patch

    from agent import update_calendar_event

    mock_context = MagicMock()

    with patch("agent.get_calendar_service", side_effect=RuntimeError("Not connected")):
        res = await update_calendar_event(mock_context, event_id="evt-123", title="New Title")
        assert "not connected" in res.lower()


@pytest.mark.asyncio
async def test_delete_calendar_event_success():
    """Verify delete_calendar_event deletes event and returns confirmation."""
    from unittest.mock import MagicMock, patch

    from agent import delete_calendar_event

    mock_service = MagicMock()
    mock_events = MagicMock()
    mock_delete = MagicMock()

    mock_service.events.return_value = mock_events
    mock_events.delete.return_value = mock_delete
    mock_delete.execute.return_value = {}

    mock_context = MagicMock()

    with patch("agent.get_calendar_service", return_value=mock_service):
        response = await delete_calendar_event(
            mock_context,
            event_id="evt-456",
        )

        assert "evt-456" in response
        assert "successfully deleted" in response

        mock_events.delete.assert_called_once_with(
            calendarId="primary",
            eventId="evt-456",
        )


@pytest.mark.asyncio
async def test_delete_calendar_event_missing_id():
    """Verify delete_calendar_event validation when event_id is empty."""
    from unittest.mock import MagicMock

    from agent import delete_calendar_event

    mock_context = MagicMock()
    res = await delete_calendar_event(mock_context, event_id="")
    assert "event id is required" in res.lower()


@pytest.mark.asyncio
async def test_delete_calendar_event_unauthenticated():
    """Verify delete_calendar_event behavior when Google Calendar is not connected."""
    from unittest.mock import MagicMock, patch

    from agent import delete_calendar_event

    mock_context = MagicMock()

    with patch("agent.get_calendar_service", side_effect=RuntimeError("Not connected")):
        res = await delete_calendar_event(mock_context, event_id="evt-456")
        assert "not connected" in res.lower()


def test_assistant_registers_create_task():
    """Verify Assistant registers create_task among its tools."""
    from agent import Assistant, create_task

    assistant = Assistant()
    tool_names = [t.name if hasattr(t, "name") else getattr(t, "__name__", str(t)) for t in assistant.tools]
    assert "create_task" in tool_names or create_task in assistant.tools


@pytest.mark.asyncio
async def test_create_task_tool_success():
    """Verify create_task tool creates task and returns confirmation message."""
    from unittest.mock import MagicMock, patch

    from agent import create_task

    mock_context = MagicMock()
    mock_service = MagicMock()

    with (
        patch("agent.get_tasks_service", return_value=mock_service),
        patch(
            "agent.create_google_task",
            return_value={"id": "task-789", "title": "Buy groceries", "due": "2026-09-15T00:00:00.000Z"},
        ) as mock_create,
    ):
        response = await create_task(mock_context, title="Buy groceries", due_date="2026-09-15")
        assert "Buy groceries" in response
        assert "successfully created" in response
        assert "2026-09-15" in response
        mock_create.assert_called_once_with(
            title="Buy groceries",
            due_date="2026-09-15",
            service=mock_service,
        )


@pytest.mark.asyncio
async def test_create_task_tool_missing_title():
    """Verify create_task validation when title is empty."""
    from unittest.mock import MagicMock

    from agent import create_task

    mock_context = MagicMock()
    res = await create_task(mock_context, title="")
    assert "task title is required" in res.lower()


@pytest.mark.asyncio
async def test_create_task_tool_unauthenticated():
    """Verify create_task behavior when Google account is not connected."""
    from unittest.mock import MagicMock, patch

    from agent import create_task

    mock_context = MagicMock()

    with patch("agent.get_tasks_service", side_effect=RuntimeError("Not connected")):
        res = await create_task(mock_context, title="Pay bills")
        assert "not connected" in res.lower()


def test_assistant_registers_list_tasks():
    """Verify Assistant registers list_tasks among its tools."""
    from agent import Assistant, list_tasks

    assistant = Assistant()
    tool_names = [t.name if hasattr(t, "name") else getattr(t, "__name__", str(t)) for t in assistant.tools]
    assert "list_tasks" in tool_names or list_tasks in assistant.tools


@pytest.mark.asyncio
async def test_list_tasks_tool_success():
    """Verify list_tasks tool retrieves tasks and returns formatted titles and due dates."""
    from unittest.mock import MagicMock, patch

    from agent import list_tasks

    mock_context = MagicMock()
    mock_service = MagicMock()

    with (
        patch("agent.get_tasks_service", return_value=mock_service),
        patch(
            "agent.list_google_tasks",
            return_value=[
                {"id": "t1", "title": "Submit report", "due": "2026-09-18T00:00:00.000Z"},
                {"id": "t2", "title": "Call mechanic"},
            ],
        ) as mock_list,
    ):
        response = await list_tasks(mock_context, max_results=10)
        assert "current tasks (2)" in response
        assert "Submit report" in response
        assert "2026-09-18" in response
        assert "Call mechanic" in response
        mock_list.assert_called_once_with(
            tasklist="@default",
            max_results=10,
            service=mock_service,
        )


@pytest.mark.asyncio
async def test_list_tasks_tool_empty():
    """Verify list_tasks tool response when task list is empty."""
    from unittest.mock import MagicMock, patch

    from agent import list_tasks

    mock_context = MagicMock()
    mock_service = MagicMock()

    with (
        patch("agent.get_tasks_service", return_value=mock_service),
        patch("agent.list_google_tasks", return_value=[]),
    ):
        response = await list_tasks(mock_context)
        assert "no tasks" in response.lower()


@pytest.mark.asyncio
async def test_list_tasks_tool_unauthenticated():
    """Verify list_tasks tool error message when unauthenticated."""
    from unittest.mock import MagicMock, patch

    from agent import list_tasks

    mock_context = MagicMock()

    with patch("agent.get_tasks_service", side_effect=RuntimeError("Not connected")):
        response = await list_tasks(mock_context)
        assert "not connected" in response.lower()


def test_assistant_registers_complete_task():
    """Verify Assistant registers complete_task among its tools."""
    from agent import Assistant, complete_task

    assistant = Assistant()
    tool_names = [t.name if hasattr(t, "name") else getattr(t, "__name__", str(t)) for t in assistant.tools]
    assert "complete_task" in tool_names or complete_task in assistant.tools


@pytest.mark.asyncio
async def test_complete_task_tool_success():
    """Verify complete_task tool marks task completed and returns confirmation message."""
    from unittest.mock import MagicMock, patch

    from agent import complete_task

    mock_context = MagicMock()
    mock_service = MagicMock()

    with (
        patch("agent.get_tasks_service", return_value=mock_service),
        patch(
            "agent.complete_google_task",
            return_value={"id": "task-xyz", "title": "File taxes", "status": "completed"},
        ) as mock_comp,
    ):
        response = await complete_task(mock_context, task_id="task-xyz")
        assert "File taxes" in response
        assert "task-xyz" in response
        assert "successfully marked as completed" in response
        mock_comp.assert_called_once_with(
            task_id="task-xyz",
            service=mock_service,
        )


@pytest.mark.asyncio
async def test_complete_task_tool_missing_id():
    """Verify complete_task tool validation when task_id is empty."""
    from unittest.mock import MagicMock

    from agent import complete_task

    mock_context = MagicMock()
    res = await complete_task(mock_context, task_id="")
    assert "task id is required" in res.lower()


@pytest.mark.asyncio
async def test_complete_task_tool_unauthenticated():
    """Verify complete_task tool error message when unauthenticated."""
    from unittest.mock import MagicMock, patch

    from agent import complete_task

    mock_context = MagicMock()

    with patch("agent.get_tasks_service", side_effect=RuntimeError("Not connected")):
        response = await complete_task(mock_context, task_id="task-xyz")
        assert "not connected" in response.lower()


def test_assistant_registers_create_email_draft():
    """Verify Assistant registers create_email_draft among its tools."""
    from agent import Assistant, create_email_draft

    assistant = Assistant()
    tool_names = [t.name if hasattr(t, "name") else getattr(t, "__name__", str(t)) for t in assistant.tools]
    assert "create_email_draft" in tool_names or create_email_draft in assistant.tools


@pytest.mark.asyncio
async def test_create_email_draft_success():
    """Verify create_email_draft creates a Gmail draft and returns confirmation."""
    from unittest.mock import MagicMock, patch

    from agent import create_email_draft

    mock_context = MagicMock()
    mock_service = MagicMock()

    with (
        patch("agent.get_gmail_service", return_value=mock_service),
        patch(
            "agent.create_gmail_draft",
            return_value={"id": "draft-abc123", "message": {"id": "msg-456"}},
        ) as mock_create,
    ):
        response = await create_email_draft(
            mock_context,
            recipient="friend@example.com",
            subject="Hello from Vaani",
            body="Just testing the draft feature!",
        )

        assert "friend@example.com" in response
        assert "Hello from Vaani" in response
        assert "successfully created" in response
        assert "draft-abc123" in response

        mock_create.assert_called_once_with(
            recipient="friend@example.com",
            subject="Hello from Vaani",
            body="Just testing the draft feature!",
            service=mock_service,
        )


@pytest.mark.asyncio
async def test_create_email_draft_missing_recipient():
    """Verify create_email_draft validation when recipient is empty."""
    from unittest.mock import MagicMock

    from agent import create_email_draft

    mock_context = MagicMock()
    res = await create_email_draft(mock_context, recipient="", subject="Hi", body="Hello")
    assert "recipient email address is required" in res.lower()


@pytest.mark.asyncio
async def test_create_email_draft_missing_subject():
    """Verify create_email_draft validation when subject is empty."""
    from unittest.mock import MagicMock

    from agent import create_email_draft

    mock_context = MagicMock()
    res = await create_email_draft(mock_context, recipient="test@test.com", subject="", body="Hello")
    assert "email subject is required" in res.lower()


@pytest.mark.asyncio
async def test_create_email_draft_missing_body():
    """Verify create_email_draft validation when body is empty."""
    from unittest.mock import MagicMock

    from agent import create_email_draft

    mock_context = MagicMock()
    res = await create_email_draft(mock_context, recipient="test@test.com", subject="Hi", body="")
    assert "email body is required" in res.lower()


@pytest.mark.asyncio
async def test_create_email_draft_unauthenticated():
    """Verify create_email_draft error message when Gmail is not connected."""
    from unittest.mock import MagicMock, patch

    from agent import create_email_draft

    mock_context = MagicMock()

    with patch("agent.get_gmail_service", side_effect=RuntimeError("Not connected")):
        response = await create_email_draft(
            mock_context,
            recipient="user@example.com",
            subject="Test",
            body="Body text",
        )
        assert "not connected" in response.lower()


def test_assistant_registers_send_email():
    """Verify Assistant registers send_email among its tools."""
    from agent import Assistant, send_email

    assistant = Assistant()
    tool_names = [t.name if hasattr(t, "name") else getattr(t, "__name__", str(t)) for t in assistant.tools]
    assert "send_email" in tool_names or send_email in assistant.tools


@pytest.mark.asyncio
async def test_send_email_success():
    """Verify send_email sends a message via Gmail API and returns confirmation."""
    from unittest.mock import MagicMock, patch

    from agent import send_email

    mock_context = MagicMock()
    mock_service = MagicMock()

    with (
        patch("agent.get_gmail_service", return_value=mock_service),
        patch(
            "agent.send_gmail_message",
            return_value={"id": "msg-sent-789", "threadId": "thread-001", "labelIds": ["SENT"]},
        ) as mock_send,
    ):
        response = await send_email(
            mock_context,
            recipient="colleague@example.com",
            subject="Meeting Notes",
            body="Here are the notes from today's meeting.",
        )

        assert "colleague@example.com" in response
        assert "Meeting Notes" in response
        assert "successfully sent" in response
        assert "msg-sent-789" in response

        mock_send.assert_called_once_with(
            recipient="colleague@example.com",
            subject="Meeting Notes",
            body="Here are the notes from today's meeting.",
            service=mock_service,
        )


@pytest.mark.asyncio
async def test_send_email_missing_recipient():
    """Verify send_email validation when recipient is empty."""
    from unittest.mock import MagicMock

    from agent import send_email

    mock_context = MagicMock()
    res = await send_email(mock_context, recipient="", subject="Hi", body="Hello")
    assert "recipient email address is required" in res.lower()


@pytest.mark.asyncio
async def test_send_email_missing_subject():
    """Verify send_email validation when subject is empty."""
    from unittest.mock import MagicMock

    from agent import send_email

    mock_context = MagicMock()
    res = await send_email(mock_context, recipient="test@test.com", subject="", body="Hello")
    assert "email subject is required" in res.lower()


@pytest.mark.asyncio
async def test_send_email_missing_body():
    """Verify send_email validation when body is empty."""
    from unittest.mock import MagicMock

    from agent import send_email

    mock_context = MagicMock()
    res = await send_email(mock_context, recipient="test@test.com", subject="Hi", body="")
    assert "email body is required" in res.lower()


@pytest.mark.asyncio
async def test_send_email_unauthenticated():
    """Verify send_email error message when Gmail is not connected."""
    from unittest.mock import MagicMock, patch

    from agent import send_email

    mock_context = MagicMock()

    with patch("agent.get_gmail_service", side_effect=RuntimeError("Not connected")):
        response = await send_email(
            mock_context,
            recipient="user@example.com",
            subject="Test",
            body="Body text",
        )
        assert "not connected" in response.lower()


@pytest.mark.asyncio
async def test_send_email_existing_draft_success():
    """Verify send_email with draft_id calls send_gmail_draft and confirms sending."""
    from unittest.mock import MagicMock, patch

    from agent import send_email

    mock_context = MagicMock()
    mock_service = MagicMock()

    with (
        patch("agent.get_gmail_service", return_value=mock_service),
        patch(
            "agent.send_gmail_draft",
            return_value={"id": "msg-from-draft-456", "threadId": "th-123"},
        ) as mock_send_draft,
    ):
        response = await send_email(
            mock_context,
            draft_id="draft-999",
            recipient="client@example.com",
            subject="Proposal",
        )

        assert "draft-999" in response
        assert "successfully sent" in response
        assert "msg-from-draft-456" in response
        mock_send_draft.assert_called_once_with(
            draft_id="draft-999",
            service=mock_service,
        )


@pytest.mark.asyncio
async def test_send_email_existing_draft_unauthenticated():
    """Verify send_email with draft_id handles unauthenticated error."""
    from unittest.mock import MagicMock, patch

    from agent import send_email

    mock_context = MagicMock()

    with patch("agent.get_gmail_service", side_effect=RuntimeError("Not connected")):
        response = await send_email(mock_context, draft_id="draft-999")
        assert "not connected" in response.lower()


@pytest.mark.asyncio
async def test_send_email_existing_draft_failure():
    """Verify send_email with draft_id handles API failure and does not confirm success."""
    from unittest.mock import MagicMock, patch

    from agent import send_email

    mock_context = MagicMock()
    mock_service = MagicMock()

    with (
        patch("agent.get_gmail_service", return_value=mock_service),
        patch("agent.send_gmail_draft", side_effect=RuntimeError("API error 404 draft not found")),
    ):
        response = await send_email(mock_context, draft_id="draft-999")
        assert "unable to send draft" in response.lower()
        assert "successfully sent" not in response


def test_assistant_registers_list_email_drafts():
    """Verify Assistant registers list_email_drafts tool."""
    from agent import Assistant, list_email_drafts

    assistant = Assistant()
    tool_names = [t.name if hasattr(t, "name") else getattr(t, "__name__", str(t)) for t in assistant.tools]
    assert "list_email_drafts" in tool_names or list_email_drafts in assistant.tools


@pytest.mark.asyncio
async def test_list_email_drafts_tool_success():
    """Verify list_email_drafts returns formatted list with IDs, recipients, and subjects."""
    from unittest.mock import MagicMock, patch

    from agent import list_email_drafts

    mock_context = MagicMock()
    mock_service = MagicMock()

    with (
        patch("agent.get_gmail_service", return_value=mock_service),
        patch(
            "agent.list_gmail_drafts",
            return_value=[
                {"id": "d-1", "recipient": "sam@example.com", "subject": "Quarterly Report"},
                {"id": "d-2", "recipient": "alex@example.com", "subject": "Coffee Catchup"},
            ],
        ) as mock_list,
    ):
        response = await list_email_drafts(mock_context)
        assert "d-1" in response
        assert "sam@example.com" in response
        assert "Quarterly Report" in response
        assert "d-2" in response
        assert "alex@example.com" in response
        mock_list.assert_called_once_with(max_results=10, service=mock_service)


@pytest.mark.asyncio
async def test_list_email_drafts_tool_empty():
    """Verify list_email_drafts message when there are no drafts."""
    from unittest.mock import MagicMock, patch

    from agent import list_email_drafts

    mock_context = MagicMock()
    mock_service = MagicMock()

    with (
        patch("agent.get_gmail_service", return_value=mock_service),
        patch("agent.list_gmail_drafts", return_value=[]),
    ):
        response = await list_email_drafts(mock_context)
        assert "no email drafts" in response.lower()


@pytest.mark.asyncio
async def test_list_email_drafts_tool_unauthenticated():
    """Verify list_email_drafts message when Gmail is not connected."""
    from unittest.mock import MagicMock, patch

    from agent import list_email_drafts

    mock_context = MagicMock()

    with patch("agent.get_gmail_service", side_effect=RuntimeError("Not connected")):
        response = await list_email_drafts(mock_context)
        assert "not connected" in response.lower()


def test_assistant_registers_update_email_draft():
    """Verify Assistant registers update_email_draft tool."""
    from agent import Assistant, update_email_draft

    assistant = Assistant()
    tool_names = [t.name if hasattr(t, "name") else getattr(t, "__name__", str(t)) for t in assistant.tools]
    assert "update_email_draft" in tool_names or update_email_draft in assistant.tools


@pytest.mark.asyncio
async def test_update_email_draft_tool_success():
    """Verify update_email_draft updates specified fields and returns confirmation."""
    from unittest.mock import MagicMock, patch

    from agent import update_email_draft

    mock_context = MagicMock()
    mock_service = MagicMock()

    with (
        patch("agent.get_gmail_service", return_value=mock_service),
        patch(
            "agent.update_gmail_draft",
            return_value={"id": "draft-update-77"},
        ) as mock_update,
    ):
        response = await update_email_draft(
            mock_context,
            draft_id="draft-update-77",
            subject="Updated Project Title",
        )
        assert "draft-update-77" in response
        assert "successfully updated" in response
        assert "Updated Project Title" in response
        mock_update.assert_called_once_with(
            draft_id="draft-update-77",
            recipient=None,
            subject="Updated Project Title",
            body=None,
            service=mock_service,
        )


@pytest.mark.asyncio
async def test_update_email_draft_tool_missing_id():
    """Verify update_email_draft returns error when draft_id is empty."""
    from unittest.mock import MagicMock

    from agent import update_email_draft

    mock_context = MagicMock()
    response = await update_email_draft(mock_context, draft_id="", subject="New Subject")
    assert "draft id is required" in response.lower()


@pytest.mark.asyncio
async def test_update_email_draft_tool_no_fields():
    """Verify update_email_draft returns error when no fields are supplied."""
    from unittest.mock import MagicMock

    from agent import update_email_draft

    mock_context = MagicMock()
    response = await update_email_draft(mock_context, draft_id="draft-123")
    assert "specify at least one field" in response.lower()


@pytest.mark.asyncio
async def test_update_email_draft_tool_unauthenticated():
    """Verify update_email_draft handles unauthenticated error."""
    from unittest.mock import MagicMock, patch

    from agent import update_email_draft

    mock_context = MagicMock()

    with patch("agent.get_gmail_service", side_effect=RuntimeError("Not connected")):
        response = await update_email_draft(mock_context, draft_id="draft-123", subject="New Subject")
        assert "not connected" in response.lower()


def test_assistant_registers_delete_email_draft():
    """Verify Assistant registers delete_email_draft tool."""
    from agent import Assistant, delete_email_draft

    assistant = Assistant()
    tool_names = [t.name if hasattr(t, "name") else getattr(t, "__name__", str(t)) for t in assistant.tools]
    assert "delete_email_draft" in tool_names or delete_email_draft in assistant.tools


@pytest.mark.asyncio
async def test_delete_email_draft_tool_success():
    """Verify delete_email_draft deletes draft and returns confirmation."""
    from unittest.mock import MagicMock, patch

    from agent import delete_email_draft

    mock_context = MagicMock()
    mock_service = MagicMock()

    with (
        patch("agent.get_gmail_service", return_value=mock_service),
        patch("agent.delete_gmail_draft") as mock_delete,
    ):
        response = await delete_email_draft(mock_context, draft_id="draft-del-55")
        assert "draft-del-55" in response
        assert "successfully deleted" in response
        mock_delete.assert_called_once_with(
            draft_id="draft-del-55",
            service=mock_service,
        )


@pytest.mark.asyncio
async def test_delete_email_draft_tool_missing_id():
    """Verify delete_email_draft returns error when draft_id is empty."""
    from unittest.mock import MagicMock

    from agent import delete_email_draft

    mock_context = MagicMock()
    response = await delete_email_draft(mock_context, draft_id="")
    assert "draft id is required" in response.lower()


@pytest.mark.asyncio
async def test_delete_email_draft_tool_unauthenticated():
    """Verify delete_email_draft handles unauthenticated error."""
    from unittest.mock import MagicMock, patch

    from agent import delete_email_draft

    mock_context = MagicMock()

    with patch("agent.get_gmail_service", side_effect=RuntimeError("Not connected")):
        response = await delete_email_draft(mock_context, draft_id="draft-del-55")
        assert "not connected" in response.lower()


def test_sarvam_voice_default_is_shubh():
    """Verify that Shubh is the default voice so existing behavior remains unchanged."""
    from unittest.mock import patch

    from agent import DEFAULT_VOICE, SARVAM_VOICE_OPTIONS, get_sarvam_speaker

    assert DEFAULT_VOICE == "male"
    assert SARVAM_VOICE_OPTIONS["male"] == "shubh"
    # When no argument is provided and no environment override is present, default is shubh
    with patch.dict("os.environ", {}, clear=False):
        assert get_sarvam_speaker() == "shubh"


def test_sarvam_voice_options_both_supported():
    """Verify both male and female voice options map to valid Sarvam speaker IDs."""
    from livekit.plugins.sarvam.tts import MODEL_SPEAKER_COMPATIBILITY

    from agent import SARVAM_VOICE_OPTIONS, get_sarvam_speaker

    assert "male" in SARVAM_VOICE_OPTIONS
    assert "female" in SARVAM_VOICE_OPTIONS

    male_speaker = get_sarvam_speaker("male")
    female_speaker = get_sarvam_speaker("female")

    assert male_speaker == "shubh"
    assert female_speaker == "ritu"

    # Both speakers must be valid speakers in the default bulbul:v3 model
    compatible_speakers = MODEL_SPEAKER_COMPATIBILITY["bulbul:v3"]["all"]
    assert male_speaker in compatible_speakers
    assert female_speaker in compatible_speakers


def test_sarvam_voice_configuration_value():
    """Verify that the single voice configuration value determines the active speaker."""
    from unittest.mock import patch

    from agent import get_sarvam_speaker

    with patch.dict("os.environ", {"VAANI_VOICE": "female"}):
        assert get_sarvam_speaker() == "ritu"

    with patch.dict("os.environ", {"VAANI_VOICE": "male"}):
        assert get_sarvam_speaker() == "shubh"


@pytest.mark.asyncio
async def test_get_recent_email_recipients_tool_empty():
    """Verify get_recent_email_recipients returns notice when memory is empty."""
    from unittest.mock import MagicMock, patch

    from agent import get_recent_email_recipients

    mock_context = MagicMock()
    with patch("agent.get_recent_recipients_db", return_value=[]):
        res = await get_recent_email_recipients(mock_context)
        assert "no recent email recipients" in res.lower()


@pytest.mark.asyncio
async def test_get_recent_email_recipients_tool_populated():
    """Verify get_recent_email_recipients formats recent recipients properly."""
    from unittest.mock import MagicMock, patch

    from agent import get_recent_email_recipients

    mock_context = MagicMock()
    fake_recipients = [
        {"name": "Alice Smith", "email": "alice@example.com"},
        {"name": "Bob Jones", "email": "bob@example.com"},
    ]
    with patch("agent.get_recent_recipients_db", return_value=fake_recipients):
        res = await get_recent_email_recipients(mock_context, limit=5)
        assert "Recent email recipients (2):" in res
        assert "Alice Smith <alice@example.com>" in res
        assert "Bob Jones <bob@example.com>" in res


@pytest.mark.asyncio
async def test_create_email_draft_with_one_matching_recent_recipient():
    """Verify create_email_draft automatically resolves a recipient name with exactly 1 match."""
    from unittest.mock import MagicMock, patch

    from agent import create_email_draft

    mock_context = MagicMock()
    mock_service = MagicMock()

    with (
        patch("agent.get_gmail_service", return_value=mock_service),
        patch("agent.resolve_email_recipient", return_value=("exact_match", {"name": "Alice Smith", "email": "alice@example.com"})),
        patch("agent.create_gmail_draft", return_value={"id": "draft-123"}) as mock_create,
        patch("agent.store_email_recipient") as mock_store,
    ):
        res = await create_email_draft(mock_context, recipient="Alice", subject="Meeting", body="See you soon")
        assert "Email draft to Alice Smith (alice@example.com)" in res
        assert "draft-123" in res
        mock_create.assert_called_once_with(
            recipient="alice@example.com",
            subject="Meeting",
            body="See you soon",
            service=mock_service,
        )
        mock_store.assert_called_once_with("alice@example.com", name="Alice Smith")


@pytest.mark.asyncio
async def test_create_email_draft_with_multiple_matching_recipients():
    """Verify create_email_draft asks user to choose when multiple recipients match."""
    from unittest.mock import MagicMock, patch

    from agent import create_email_draft

    mock_context = MagicMock()
    matches = [
        {"name": "Alice Smith", "email": "alice.smith@example.com"},
        {"name": "Alice Wonder", "email": "alice.wonder@example.com"},
    ]

    with (
        patch("agent.resolve_email_recipient", return_value=("multiple_matches", matches)),
        patch("agent.create_gmail_draft") as mock_create,
    ):
        res = await create_email_draft(mock_context, recipient="Alice", subject="Hello", body="Body")
        assert "Multiple recent recipients match 'Alice'" in res
        assert "alice.smith@example.com" in res
        assert "alice.wonder@example.com" in res
        assert "Please specify which recipient" in res
        mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_create_email_draft_with_unknown_recipient():
    """Verify create_email_draft prompts for email address if recipient is new/unknown."""
    from unittest.mock import MagicMock, patch

    from agent import create_email_draft

    mock_context = MagicMock()

    with (
        patch("agent.resolve_email_recipient", return_value=("no_match", [])),
        patch("agent.create_gmail_draft") as mock_create,
    ):
        res = await create_email_draft(mock_context, recipient="Charlie", subject="Hello", body="Body")
        assert "No recent recipient found for 'Charlie'" in res
        assert "Please provide their email address" in res
        mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_send_email_with_one_matching_recent_recipient():
    """Verify send_email automatically resolves a recipient name with 1 match and sends."""
    from unittest.mock import MagicMock, patch

    from agent import send_email

    mock_context = MagicMock()
    mock_service = MagicMock()

    with (
        patch("agent.get_gmail_service", return_value=mock_service),
        patch("agent.resolve_email_recipient", return_value=("exact_match", {"name": "Bob Jones", "email": "bob@example.com"})),
        patch("agent.send_gmail_message", return_value={"id": "msg-789"}) as mock_send,
        patch("agent.store_email_recipient") as mock_store,
    ):
        res = await send_email(mock_context, recipient="Bob", subject="Updates", body="Status report")
        assert "Email to Bob Jones (bob@example.com)" in res
        assert "msg-789" in res
        mock_send.assert_called_once_with(
            recipient="bob@example.com",
            subject="Updates",
            body="Status report",
            service=mock_service,
        )
        mock_store.assert_called_once_with("bob@example.com", name="Bob Jones")


@pytest.mark.asyncio
async def test_send_email_with_multiple_matching_recipients():
    """Verify send_email returns matching choices if multiple recipients match."""
    from unittest.mock import MagicMock, patch

    from agent import send_email

    mock_context = MagicMock()
    matches = [
        {"name": "Bob Martin", "email": "bm@example.com"},
        {"name": "Bob Dylan", "email": "bd@example.com"},
    ]

    with (
        patch("agent.resolve_email_recipient", return_value=("multiple_matches", matches)),
        patch("agent.send_gmail_message") as mock_send,
    ):
        res = await send_email(mock_context, recipient="Bob", subject="Subject", body="Body")
        assert "Multiple recent recipients match 'Bob'" in res
        assert "bm@example.com" in res
        assert "bd@example.com" in res
        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_send_email_with_unknown_recipient():
    """Verify send_email prompts for email address if recipient name is unknown."""
    from unittest.mock import MagicMock, patch

    from agent import send_email

    mock_context = MagicMock()

    with (
        patch("agent.resolve_email_recipient", return_value=("no_match", [])),
        patch("agent.send_gmail_message") as mock_send,
    ):
        res = await send_email(mock_context, recipient="David", subject="Subject", body="Body")
        assert "No recent recipient found for 'David'" in res
        assert "Please provide their email address" in res
        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_recipient_stored_on_draft_creation_direct_email(tmp_path):
    """Verify recipient is stored in SQLite when draft is created with email address."""
    from unittest.mock import MagicMock, patch

    from agent import create_email_draft
    from memory import init_db, get_recent_email_recipients as get_recipients

    db_path = tmp_path / "test_memory.db"
    init_db(db_path)

    mock_context = MagicMock()
    mock_service = MagicMock()

    with (
        patch("agent.get_gmail_service", return_value=mock_service),
        patch("agent.create_gmail_draft", return_value={"id": "draft-abc"}),
        patch("agent.store_email_recipient", side_effect=lambda em, name="": __import__("memory").store_email_recipient(em, name=name, db_path=db_path)),
    ):
        await create_email_draft(mock_context, recipient="Eve <eve@example.com>", subject="Hello", body="Content")
        recent = get_recipients(limit=5, db_path=db_path)
        assert len(recent) == 1
        assert recent[0]["email"] == "eve@example.com"
        assert recent[0]["name"] == "Eve"


def test_assistant_registers_get_recent_email_recipients():
    """Verify Assistant registers get_recent_email_recipients tool."""
    from agent import Assistant, get_recent_email_recipients

    assistant = Assistant()
    tool_names = [t.name if hasattr(t, "name") else getattr(t, "__name__", str(t)) for t in assistant.tools]
    assert "get_recent_email_recipients" in tool_names or get_recent_email_recipients in assistant.tools




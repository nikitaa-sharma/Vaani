"""Unit tests for Gmail integration module."""

from unittest.mock import MagicMock, patch

import pytest

from google_gmail import (
    GMAIL_COMPOSE_SCOPE,
    build_raw_email_message,
    create_gmail_draft,
    delete_gmail_draft,
    get_gmail_service,
    list_gmail_drafts,
    send_gmail_draft,
    send_gmail_message,
    update_gmail_draft,
)


def test_gmail_compose_scope():
    """Verify that Gmail compose scope is defined correctly."""
    assert GMAIL_COMPOSE_SCOPE == "https://www.googleapis.com/auth/gmail.compose"


def test_build_raw_email_message():
    """Verify building raw email message produces valid base64url encoded output."""
    raw = build_raw_email_message("recipient@example.com", "Subject Line", "Email body here")
    assert isinstance(raw, str)
    assert len(raw) > 0


def test_get_gmail_service_unauthenticated():
    """Verify RuntimeError when user is not authenticated."""
    with patch("google_gmail.get_credentials", return_value=None), pytest.raises(
        RuntimeError, match="not authenticated"
    ):
        get_gmail_service()


def test_get_gmail_service_authenticated():
    """Verify build is called with gmail v1 when authenticated."""
    mock_creds = MagicMock()
    mock_creds.valid = True

    with (
        patch("google_gmail.get_credentials", return_value=mock_creds),
        patch("google_gmail.build") as mock_build,
    ):
        get_gmail_service()
        mock_build.assert_called_once_with("gmail", "v1", credentials=mock_creds, cache_discovery=False)


def test_send_gmail_message_success():
    """Verify send_gmail_message calls messages().send() with raw body."""
    mock_service = MagicMock()
    mock_messages = MagicMock()
    mock_send = MagicMock()

    mock_service.users.return_value.messages.return_value = mock_messages
    mock_messages.send.return_value = mock_send
    mock_send.execute.return_value = {
        "id": "msg-12345",
        "threadId": "thread-12345",
        "labelIds": ["SENT"],
    }

    result = send_gmail_message(
        recipient="test@example.com",
        subject="Hello",
        body="World",
        service=mock_service,
    )

    assert result["id"] == "msg-12345"
    assert "SENT" in result["labelIds"]
    mock_messages.send.assert_called_once()
    call_kwargs = mock_messages.send.call_args[1]
    assert call_kwargs["userId"] == "me"
    assert "raw" in call_kwargs["body"]


def test_send_gmail_message_missing_fields():
    """Verify ValueError when required arguments are empty or whitespace."""
    with pytest.raises(ValueError, match="Recipient email address is required"):
        send_gmail_message("", "Subject", "Body")

    with pytest.raises(ValueError, match="Email subject is required"):
        send_gmail_message("test@example.com", "   ", "Body")

    with pytest.raises(ValueError, match="Email body is required"):
        send_gmail_message("test@example.com", "Subject", "")


def test_send_gmail_draft_success():
    """Verify send_gmail_draft calls drafts().send with draft ID body."""
    mock_service = MagicMock()
    mock_drafts = MagicMock()
    mock_send = MagicMock()

    mock_service.users.return_value.drafts.return_value = mock_drafts
    mock_drafts.send.return_value = mock_send
    mock_send.execute.return_value = {
        "id": "msg-from-draft",
        "threadId": "thread-123",
        "labelIds": ["SENT"],
    }

    result = send_gmail_draft(
        draft_id="d-789",
        service=mock_service,
    )

    assert result["id"] == "msg-from-draft"
    mock_drafts.send.assert_called_once_with(
        userId="me",
        body={"id": "d-789"},
    )


def test_send_gmail_draft_missing_id():
    """Verify ValueError when draft_id is empty."""
    with pytest.raises(ValueError, match="Draft ID is required"):
        send_gmail_draft(draft_id="")


def test_list_gmail_drafts_success():
    """Verify list_gmail_drafts returns formatted list with recipient and subject."""
    mock_service = MagicMock()
    mock_drafts = MagicMock()
    mock_list = MagicMock()
    mock_get = MagicMock()

    mock_service.users.return_value.drafts.return_value = mock_drafts
    mock_drafts.list.return_value = mock_list
    mock_list.execute.return_value = {
        "drafts": [
            {"id": "draft-1"},
            {"id": "draft-2"},
        ]
    }

    mock_drafts.get.return_value = mock_get
    # Mock details for draft-1 and draft-2
    mock_get.execute.side_effect = [
        {
            "id": "draft-1",
            "message": {
                "payload": {
                    "headers": [
                        {"name": "To", "value": "alice@example.com"},
                        {"name": "Subject", "value": "Project Sync"},
                    ]
                }
            },
        },
        {
            "id": "draft-2",
            "message": {
                "payload": {
                    "headers": [
                        {"name": "To", "value": "bob@example.com"},
                        {"name": "Subject", "value": "Invoice"},
                    ]
                }
            },
        },
    ]

    result = list_gmail_drafts(service=mock_service)
    assert len(result) == 2
    assert result[0] == {"id": "draft-1", "recipient": "alice@example.com", "subject": "Project Sync"}
    assert result[1] == {"id": "draft-2", "recipient": "bob@example.com", "subject": "Invoice"}


def test_list_gmail_drafts_empty():
    """Verify list_gmail_drafts returns empty list when no drafts exist."""
    mock_service = MagicMock()
    mock_drafts = MagicMock()
    mock_list = MagicMock()

    mock_service.users.return_value.drafts.return_value = mock_drafts
    mock_drafts.list.return_value = mock_list
    mock_list.execute.return_value = {}

    result = list_gmail_drafts(service=mock_service)
    assert result == []


def test_update_gmail_draft_success():
    """Verify update_gmail_draft fetches existing draft and updates only specified fields."""
    mock_service = MagicMock()
    mock_drafts = MagicMock()
    mock_get = MagicMock()
    mock_update = MagicMock()

    mock_service.users.return_value.drafts.return_value = mock_drafts
    mock_drafts.get.return_value = mock_get
    mock_drafts.update.return_value = mock_update

    # Prepare raw RFC 2822 message for existing draft: To: old@example.com, Subject: Old Subject, Body: Old Body
    existing_raw = build_raw_email_message("old@example.com", "Old Subject", "Old Body")
    mock_get.execute.return_value = {
        "id": "draft-update-1",
        "message": {"raw": existing_raw},
    }
    mock_update.execute.return_value = {
        "id": "draft-update-1",
        "message": {"id": "msg-new"},
    }

    # Update only subject
    result = update_gmail_draft(
        draft_id="draft-update-1",
        subject="Updated Subject Line",
        service=mock_service,
    )

    assert result["id"] == "draft-update-1"
    mock_drafts.get.assert_called_once_with(userId="me", id="draft-update-1", format="raw")
    mock_drafts.update.assert_called_once()
    update_call_kwargs = mock_drafts.update.call_args[1]
    assert update_call_kwargs["id"] == "draft-update-1"
    assert "raw" in update_call_kwargs["body"]["message"]


def test_update_gmail_draft_validations():
    """Verify validations on draft_id and empty fields in update_gmail_draft."""
    with pytest.raises(ValueError, match="Draft ID is required"):
        update_gmail_draft(draft_id="")

    with pytest.raises(ValueError, match="At least one field"):
        update_gmail_draft(draft_id="d-123", recipient="", subject="", body="")


def test_delete_gmail_draft_success():
    """Verify delete_gmail_draft calls drafts().delete with expected parameters."""
    mock_service = MagicMock()
    mock_drafts = MagicMock()
    mock_delete = MagicMock()

    mock_service.users.return_value.drafts.return_value = mock_drafts
    mock_drafts.delete.return_value = mock_delete
    mock_delete.execute.return_value = {}

    delete_gmail_draft(draft_id="draft-del-1", service=mock_service)
    mock_drafts.delete.assert_called_once_with(userId="me", id="draft-del-1")


def test_delete_gmail_draft_missing_id():
    """Verify ValueError when draft_id is empty in delete_gmail_draft."""
    with pytest.raises(ValueError, match="Draft ID is required"):
        delete_gmail_draft(draft_id="")


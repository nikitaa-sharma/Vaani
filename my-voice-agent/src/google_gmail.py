"""Gmail integration module for Vaani.

Provides integration with the Gmail API using existing backend Google OAuth
credentials and the Gmail compose scope (https://www.googleapis.com/auth/gmail.compose).
Supports creating drafts and sending emails.
"""

from __future__ import annotations

import base64
import logging
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from googleapiclient.discovery import Resource, build

try:
    from google_calendar_auth import get_credentials
except ImportError:
    from src.google_calendar_auth import get_credentials

logger = logging.getLogger("google_gmail")

# Scope required for creating and managing drafts in Gmail
GMAIL_COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
SCOPES = [GMAIL_COMPOSE_SCOPE]


def build_raw_email_message(recipient: str, subject: str, body: str) -> str:
    """Construct an RFC 2822 email message and return it as a base64url-encoded string.

    Args:
        recipient: Destination email address.
        subject: Email subject line.
        body: Plain text body of the email.

    Returns:
        Base64url-encoded string suitable for the Gmail API 'raw' message field.
    """
    message = EmailMessage()
    message.set_content(body)
    message["To"] = recipient.strip()
    message["Subject"] = subject.strip()

    return base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")


def get_gmail_service(token_path: Path | str | None = None) -> Resource:
    """Construct an authorized Gmail API Resource service.

    Args:
        token_path: Optional custom path to credentials file.

    Returns:
        googleapiclient.discovery.Resource for Gmail API v1.

    Raises:
        RuntimeError: If user is not authenticated.
    """
    creds = get_credentials(token_path=token_path, auto_refresh=True)
    if not creds:
        raise RuntimeError(
            "Google account is not authenticated. Complete Google OAuth flow first."
        )

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def create_gmail_draft(
    recipient: str,
    subject: str,
    body: str,
    service: Resource | None = None,
    token_path: Path | str | None = None,
    user_id: str = "me",
) -> dict[str, Any]:
    """Create an email draft in the user's Gmail account.

    Args:
        recipient: Destination email address.
        subject: Subject line of the email.
        body: Text content/body of the email.
        service: Optional pre-constructed Gmail service.
        token_path: Optional path to credentials file.
        user_id: The user's email address or 'me' for the authenticated user.

    Returns:
        The created draft resource dict returned by the Gmail API.

    Raises:
        ValueError: If recipient, subject, or body is missing.
        RuntimeError: If not authenticated or API call fails.
    """
    if not recipient or not recipient.strip():
        raise ValueError("Recipient email address is required.")
    if not subject or not subject.strip():
        raise ValueError("Email subject is required.")
    if not body or not body.strip():
        raise ValueError("Email body is required.")

    if service is None:
        service = get_gmail_service(token_path=token_path)

    raw_message = build_raw_email_message(
        recipient=recipient.strip(),
        subject=subject.strip(),
        body=body.strip(),
    )
    draft_body = {"message": {"raw": raw_message}}

    return service.users().drafts().create(userId=user_id, body=draft_body).execute()


def send_gmail_message(
    recipient: str,
    subject: str,
    body: str,
    service: Resource | None = None,
    token_path: Path | str | None = None,
    user_id: str = "me",
) -> dict[str, Any]:
    """Send an email from the user's Gmail account.

    Args:
        recipient: Destination email address.
        subject: Subject line of the email.
        body: Text content/body of the email.
        service: Optional pre-constructed Gmail service.
        token_path: Optional path to credentials file.
        user_id: The user's email address or 'me' for the authenticated user.

    Returns:
        The sent message resource dict returned by the Gmail API.

    Raises:
        ValueError: If recipient, subject, or body is missing.
        RuntimeError: If not authenticated or API call fails.
    """
    if not recipient or not recipient.strip():
        raise ValueError("Recipient email address is required.")
    if not subject or not subject.strip():
        raise ValueError("Email subject is required.")
    if not body or not body.strip():
        raise ValueError("Email body is required.")

    if service is None:
        service = get_gmail_service(token_path=token_path)

    raw_message = build_raw_email_message(
        recipient=recipient.strip(),
        subject=subject.strip(),
        body=body.strip(),
    )
    message_body = {"raw": raw_message}

    return service.users().messages().send(userId=user_id, body=message_body).execute()


def send_gmail_draft(
    draft_id: str,
    service: Resource | None = None,
    token_path: Path | str | None = None,
    user_id: str = "me",
) -> dict[str, Any]:
    """Send an existing Gmail draft via the Gmail drafts.send API operation.

    Once sent, the draft is removed from Drafts and becomes a sent message.

    Args:
        draft_id: The unique ID of the draft to send.
        service: Optional pre-constructed Gmail service.
        token_path: Optional path to credentials file.
        user_id: The user's email address or 'me' for the authenticated user.

    Returns:
        The sent message resource dict returned by the Gmail API.

    Raises:
        ValueError: If draft_id is missing or empty.
        RuntimeError: If not authenticated or API call fails.
    """
    if not draft_id or not draft_id.strip():
        raise ValueError("Draft ID is required to send a draft.")

    if service is None:
        service = get_gmail_service(token_path=token_path)

    return service.users().drafts().send(userId=user_id, body={"id": draft_id.strip()}).execute()


def _extract_draft_headers(draft_detail: dict[str, Any]) -> tuple[str, str]:
    """Extract recipient (To) and Subject headers from a draft detail dict."""
    recipient = ""
    subject = ""

    message = draft_detail.get("message", {})
    payload = message.get("payload", {})
    headers = payload.get("headers", [])

    if isinstance(headers, list):
        for h in headers:
            name = (h.get("name") or "").lower()
            if name == "to" and not recipient:
                recipient = h.get("value", "")
            elif name == "subject" and not subject:
                subject = h.get("value", "")
    elif isinstance(headers, dict):
        recipient = headers.get("To", headers.get("to", ""))
        subject = headers.get("Subject", headers.get("subject", ""))

    return recipient, subject


def _parse_draft_content(existing_draft: dict[str, Any]) -> tuple[str, str, str]:
    """Parse recipient, subject, and body from an existing draft resource dict."""
    import email

    message = existing_draft.get("message", {})
    raw_b64 = message.get("raw")
    if raw_b64:
        try:
            padded = raw_b64 + "=" * (-len(raw_b64) % 4)
            raw_bytes = base64.urlsafe_b64decode(padded.encode("utf-8"))
            parsed_msg = email.message_from_bytes(raw_bytes)
            to_val = parsed_msg.get("To", "")
            subj_val = parsed_msg.get("Subject", "")
            body_val = ""
            if parsed_msg.is_multipart():
                for part in parsed_msg.walk():
                    if part.get_content_type() == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            body_val = payload.decode("utf-8", errors="replace")
                        break
            else:
                payload = parsed_msg.get_payload(decode=True)
                if payload:
                    body_val = payload.decode("utf-8", errors="replace")
                elif isinstance(parsed_msg.get_payload(), str):
                    body_val = parsed_msg.get_payload()
            return to_val, subj_val, body_val
        except Exception as e:
            logger.warning(f"Failed to parse raw draft content: {e}")

    recipient, subject = _extract_draft_headers(existing_draft)
    body_val = message.get("snippet", "")
    return recipient, subject, body_val


def list_gmail_drafts(
    max_results: int = 10,
    service: Resource | None = None,
    token_path: Path | str | None = None,
    user_id: str = "me",
) -> list[dict[str, Any]]:
    """List current Gmail drafts with their ID, recipient, and subject.

    Args:
        max_results: Maximum number of drafts to return (default 10).
        service: Optional pre-constructed Gmail service.
        token_path: Optional path to credentials file.
        user_id: The user's email address or 'me' for the authenticated user.

    Returns:
        A list of dicts with 'id', 'recipient', and 'subject' for each draft.

    Raises:
        RuntimeError: If not authenticated or API call fails.
    """
    if service is None:
        service = get_gmail_service(token_path=token_path)

    response = service.users().drafts().list(userId=user_id, maxResults=max_results).execute()
    drafts_meta = response.get("drafts", [])
    results: list[dict[str, Any]] = []

    for item in drafts_meta:
        d_id = item.get("id")
        if not d_id:
            continue
        try:
            detail = service.users().drafts().get(userId=user_id, id=d_id, format="full").execute()
        except Exception as err:
            logger.warning(f"Could not retrieve details for draft {d_id}: {err}")
            detail = item

        recipient, subject = _extract_draft_headers(detail)
        results.append({
            "id": d_id,
            "recipient": recipient,
            "subject": subject,
        })

    return results


def update_gmail_draft(
    draft_id: str,
    recipient: str | None = None,
    subject: str | None = None,
    body: str | None = None,
    service: Resource | None = None,
    token_path: Path | str | None = None,
    user_id: str = "me",
) -> dict[str, Any]:
    """Update only the provided fields of an existing Gmail draft.

    Args:
        draft_id: The unique ID of the draft to update.
        recipient: Optional new recipient email address.
        subject: Optional new subject line.
        body: Optional new body text.
        service: Optional pre-constructed Gmail service.
        token_path: Optional path to credentials file.
        user_id: The user's email address or 'me' for the authenticated user.

    Returns:
        The updated draft resource dict returned by the Gmail API.

    Raises:
        ValueError: If draft_id is empty or no fields were provided to update.
        RuntimeError: If not authenticated or API call fails.
    """
    if not draft_id or not draft_id.strip():
        raise ValueError("Draft ID is required to update a draft.")

    has_recipient = recipient is not None and bool(recipient.strip())
    has_subject = subject is not None and bool(subject.strip())
    has_body = body is not None and bool(body.strip())

    if not (has_recipient or has_subject or has_body):
        raise ValueError("At least one field (recipient, subject, or body) must be provided to update.")

    if service is None:
        service = get_gmail_service(token_path=token_path)

    existing = service.users().drafts().get(userId=user_id, id=draft_id.strip(), format="raw").execute()
    existing_to, existing_subj, existing_body = _parse_draft_content(existing)

    final_to = recipient.strip() if has_recipient else existing_to
    final_subj = subject.strip() if has_subject else existing_subj
    final_body = body.strip() if has_body else existing_body

    raw_message = build_raw_email_message(
        recipient=final_to,
        subject=final_subj,
        body=final_body,
    )
    draft_body = {"id": draft_id.strip(), "message": {"raw": raw_message}}

    return service.users().drafts().update(
        userId=user_id,
        id=draft_id.strip(),
        body=draft_body,
    ).execute()


def delete_gmail_draft(
    draft_id: str,
    service: Resource | None = None,
    token_path: Path | str | None = None,
    user_id: str = "me",
) -> None:
    """Delete a Gmail draft by ID using the Gmail API.

    Args:
        draft_id: The unique ID of the draft to delete.
        service: Optional pre-constructed Gmail service.
        token_path: Optional path to credentials file.
        user_id: The user's email address or 'me' for the authenticated user.

    Raises:
        ValueError: If draft_id is missing or empty.
        RuntimeError: If not authenticated or API call fails.
    """
    if not draft_id or not draft_id.strip():
        raise ValueError("Draft ID is required to delete a draft.")

    if service is None:
        service = get_gmail_service(token_path=token_path)

    service.users().drafts().delete(userId=user_id, id=draft_id.strip()).execute()


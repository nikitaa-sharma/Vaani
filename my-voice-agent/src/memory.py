import email.utils
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "agent_memory.db"


def _get_connection(db_path: Optional[Path | str] = None) -> sqlite3.Connection:
    target_path = Path(db_path) if db_path else DEFAULT_DB_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(target_path))


def init_db(db_path: Optional[Path | str] = None) -> None:
    """Initialize the SQLite database and create tables if they do not exist."""
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS email_recipients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()


def store_memory(content: str, db_path: Optional[Path | str] = None) -> int:
    """Store a simple memory string in the database.

    Args:
        content: The text memory to store.
        db_path: Optional custom path to SQLite database.

    Returns:
        The row ID of the inserted memory.
    """
    init_db(db_path)
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO memories (content) VALUES (?)",
            (content.strip(),),
        )
        conn.commit()
        return cursor.lastrowid or 0


# Convenient aliases
save_memory = store_memory
add_memory = store_memory


def retrieve_memories(
    limit: int = 10, db_path: Optional[Path | str] = None
) -> List[str]:
    """Retrieve the most recent memories as a list of strings.

    Args:
        limit: Maximum number of memories to retrieve (default 10).
        db_path: Optional custom path to SQLite database.

    Returns:
        A list of memory content strings.
    """
    init_db(db_path)
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT content FROM memories ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = cursor.fetchall()
        return [row[0] for row in rows]


# Convenient aliases
get_memories = retrieve_memories


def search_memories(
    query: str, limit: int = 10, db_path: Optional[Path | str] = None
) -> List[str]:
    """Search stored memories by keyword.

    Args:
        query: The substring to search for.
        limit: Maximum number of matching memories to return.
        db_path: Optional custom path to SQLite database.

    Returns:
        A list of matching memory content strings.
    """
    init_db(db_path)
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT content FROM memories WHERE content LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{query}%", limit),
        )
        rows = cursor.fetchall()
        return [row[0] for row in rows]


def clear_memories(db_path: Optional[Path | str] = None) -> None:
    """Clear all records from the memories table."""
    init_db(db_path)
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memories")
        conn.commit()


def delete_memory(content: str, db_path: Optional[Path | str] = None) -> int:
    """Delete matching memory records from the database.

    Args:
        content: The text content or substring to delete.
        db_path: Optional custom path to SQLite database.

    Returns:
        The number of deleted records.
    """
    init_db(db_path)
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM memories WHERE content = ? OR content LIKE ?",
            (content.strip(), f"%{content.strip()}%"),
        )
        conn.commit()
        return cursor.rowcount


delete_user_memory = delete_memory


def parse_name_and_email(raw_input: str) -> Tuple[str, str]:
    """Extract contact name and clean email address from user or raw input.

    Handles inputs like:
      - 'John Doe <john@example.com>' -> ('John Doe', 'john@example.com')
      - 'john@example.com' -> ('', 'john@example.com')
      - 'John Doe' -> ('John Doe', '')
    """
    cleaned = raw_input.strip()
    if "@" in cleaned:
        name, addr = email.utils.parseaddr(cleaned)
        if addr and "@" in addr:
            return name.strip(), addr.strip().lower()
        parts = cleaned.split()
        for p in parts:
            if "@" in p:
                addr = p.strip("<>,;()")
                other_parts = [x for x in parts if x != p]
                return " ".join(other_parts).strip(), addr.lower()
    return cleaned, ""


def store_email_recipient(
    recipient_or_name: str = "",
    email_or_name: str = "",
    *,
    name: str = "",
    email: str = "",
    db_path: Optional[Path | str] = None,
) -> int:
    """Store or update a recent email recipient in SQLite.

    Accepts (name, email), (email, name), or keyword arguments name=..., email=...
    If the recipient email already exists, updates last_used to current timestamp
    and updates the name if a non-empty name is provided.

    Args:
        recipient_or_name: Contact name or email address.
        email_or_name: Contact email address or name.
        name: Contact name (keyword argument).
        email: Contact email address (keyword argument).
        db_path: Optional custom path to SQLite database.

    Returns:
        The row ID of the inserted or updated recipient.
    """
    resolved_email = email
    resolved_name = name

    if recipient_or_name:
        if "@" in recipient_or_name:
            if not resolved_email:
                resolved_email = recipient_or_name
            if not resolved_name and email_or_name:
                resolved_name = email_or_name
        else:
            if not resolved_name:
                resolved_name = recipient_or_name
            if not resolved_email and email_or_name:
                resolved_email = email_or_name

    if not resolved_email and email_or_name and "@" in email_or_name:
        resolved_email = email_or_name

    clean_name = (resolved_name or "").strip()
    clean_email = (resolved_email or "").strip().lower()

    if not clean_email or "@" not in clean_email:
        raise ValueError("A valid email address is required to store an email recipient.")

    # If name is empty, derive a default from the email prefix
    if not clean_name:
        clean_name = clean_email.split("@")[0].capitalize()

    init_db(db_path)
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO email_recipients (name, email, last_used)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(email) DO UPDATE SET
                name = CASE WHEN excluded.name != '' THEN excluded.name ELSE email_recipients.name END,
                last_used = CURRENT_TIMESTAMP;
            """,
            (clean_name, clean_email),
        )
        conn.commit()
        return cursor.lastrowid or 0


def get_recent_email_recipients(
    limit: int = 5,
    db_path: Optional[Path | str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve the most recently used email recipients.

    Args:
        limit: Maximum number of recipients to retrieve (default 5).
        db_path: Optional custom path to SQLite database.

    Returns:
        A list of dicts with 'name', 'email', and 'last_used'.
    """
    init_db(db_path)
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT name, email, last_used
            FROM email_recipients
            ORDER BY last_used DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        return [
            {"name": row[0], "email": row[1], "last_used": row[2]}
            for row in rows
        ]


def match_email_recipients(
    name_query: str,
    db_path: Optional[Path | str] = None,
) -> List[Dict[str, str]]:
    """Search stored email recipients by name or email.

    Performs case-insensitive matching:
    - Exact match on name or email
    - Substring match on name

    Args:
        name_query: The name or query to match.
        db_path: Optional custom path to SQLite database.

    Returns:
        List of matching recipient dicts with 'name' and 'email'.
    """
    q = name_query.strip().lower()
    if not q:
        return []

    init_db(db_path)
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT name, email, last_used
            FROM email_recipients
            WHERE LOWER(name) = ? OR LOWER(email) = ?
            ORDER BY last_used DESC, id DESC
            """,
            (q, q),
        )
        exact_matches = [
            {"name": r[0], "email": r[1]}
            for r in cursor.fetchall()
        ]

        cursor.execute(
            """
            SELECT name, email, last_used
            FROM email_recipients
            WHERE (LOWER(name) LIKE ? OR LOWER(email) LIKE ?)
              AND LOWER(name) != ? AND LOWER(email) != ?
            ORDER BY last_used DESC, id DESC
            """,
            (f"%{q}%", f"%{q}%", q, q),
        )
        partial_matches = [
            {"name": r[0], "email": r[1]}
            for r in cursor.fetchall()
        ]

        return exact_matches + partial_matches


def resolve_email_recipient(
    recipient_input: str,
    db_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """Resolve an email recipient from user input.

    Scenarios:
    1. Input contains a valid email address:
       -> status: 'resolved'
       -> Automatically records/updates the recipient in memory.
    2. Input is a name matching exactly one stored recipient:
       -> status: 'resolved'
       -> Uses that recipient automatically.
    3. Input matches multiple stored recipients:
       -> status: 'multiple_matches'
       -> Returns all candidate matches.
    4. Input does not match any stored recipient and has no email address:
       -> status: 'unknown'
       -> Asks user for their email address so it can be saved for future use.

    Args:
        recipient_input: The user-provided recipient string (name, email, or 'Name <email>').
        db_path: Optional custom path to SQLite database.

    Returns:
        Dict with 'status', 'recipient' (if resolved), 'matches' (if multiple),
        and 'message'.
    """
    raw = recipient_input.strip()
    if not raw:
        return {
            "status": "unknown",
            "recipient": None,
            "matches": [],
            "message": "A recipient name or email address is required.",
        }

    parsed_name, parsed_email = parse_name_and_email(raw)
    if parsed_email and "@" in parsed_email:
        final_name = parsed_name if parsed_name else parsed_email.split("@")[0].capitalize()
        store_email_recipient(final_name, parsed_email, db_path=db_path)
        return {
            "status": "resolved",
            "recipient": {"name": final_name, "email": parsed_email},
            "matches": [{"name": final_name, "email": parsed_email}],
            "message": f"Using recipient {final_name} ({parsed_email}).",
        }

    matches = match_email_recipients(raw, db_path=db_path)

    seen = set()
    unique_matches = []
    for m in matches:
        if m["email"] not in seen:
            seen.add(m["email"])
            unique_matches.append(m)

    if len(unique_matches) == 1:
        match = unique_matches[0]
        store_email_recipient(match["name"], match["email"], db_path=db_path)
        return {
            "status": "resolved",
            "recipient": match,
            "matches": [match],
            "message": f"Found saved recipient {match['name']} ({match['email']}).",
        }
    elif len(unique_matches) > 1:
        formatted_list = ", ".join(f"{m['name']} ({m['email']})" for m in unique_matches)
        return {
            "status": "multiple_matches",
            "recipient": None,
            "matches": unique_matches,
            "message": f"Found multiple recipients matching '{raw}': {formatted_list}. Please choose one.",
        }
    else:
        return {
            "status": "unknown",
            "recipient": None,
            "matches": [],
            "message": f"I don't have an email address for '{raw}'. Please provide their email address, and I will save it for future use.",
        }


class MemoryDB:
    """Convenience class for managing a persistent local SQLite memory store."""

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        init_db(self.db_path)

    def store_memory(self, content: str) -> int:
        return store_memory(content, self.db_path)

    def add_memory(self, content: str) -> int:
        return store_memory(content, self.db_path)

    def retrieve_memories(self, limit: int = 10) -> List[str]:
        return retrieve_memories(limit, self.db_path)

    def get_memories(self, limit: int = 10) -> List[str]:
        return retrieve_memories(limit, self.db_path)

    def search_memories(self, query: str, limit: int = 10) -> List[str]:
        return search_memories(query, limit, self.db_path)

    def delete_memory(self, content: str) -> int:
        return delete_memory(content, self.db_path)

    def clear_memories(self) -> None:
        clear_memories(self.db_path)

    def store_email_recipient(
        self,
        recipient_or_name: str = "",
        email_or_name: str = "",
        *,
        name: str = "",
        email: str = "",
    ) -> int:
        return store_email_recipient(
            recipient_or_name=recipient_or_name,
            email_or_name=email_or_name,
            name=name,
            email=email,
            db_path=self.db_path,
        )

    def get_recent_email_recipients(self, limit: int = 5) -> List[Dict[str, Any]]:
        return get_recent_email_recipients(limit, self.db_path)

    def match_email_recipients(self, name_query: str) -> List[Dict[str, str]]:
        return match_email_recipients(name_query, self.db_path)

    def resolve_email_recipient(self, recipient_input: str) -> Dict[str, Any]:
        return resolve_email_recipient(recipient_input, self.db_path)


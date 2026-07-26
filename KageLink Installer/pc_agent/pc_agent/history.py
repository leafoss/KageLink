from __future__ import annotations

import sqlite3
from contextlib import closing
import threading
from datetime import datetime, timezone
from pathlib import Path


VALID_CHANNELS = {"ooc", "ic"}


class HistoryStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    channel TEXT NOT NULL DEFAULT 'ooc',
                    text TEXT NOT NULL,
                    resynchronized INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(messages)").fetchall()
            }
            if "channel" not in columns:
                connection.execute(
                    "ALTER TABLE messages ADD COLUMN channel TEXT NOT NULL DEFAULT 'ooc'"
                )
            connection.execute(
                """
                UPDATE messages
                SET channel = 'ic'
                WHERE channel = 'ooc'
                  AND ltrim(text) LIKE '(*%'
                  AND rtrim(text) LIKE '%*)'
                """
            )
            connection.commit()

    @staticmethod
    def _channel(value: str) -> str:
        normalized = str(value or "ooc").strip().lower()
        return normalized if normalized in VALID_CHANNELS else "ooc"

    def max_message_id(self) -> int:
        with self._lock, closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(id), 0) AS max_id FROM messages"
            ).fetchone()
        return int(row["max_id"] if row is not None else 0)

    def ensure_next_message_id_after(self, floor: int) -> int:
        """Ensure future AUTOINCREMENT IDs are strictly greater than ``floor``.

        LeafOS Processor evidence uses KageLink message IDs as durable numeric
        identities. A fresh/reinstalled local SQLite database can otherwise start
        again at 1 while an existing Vault still has a much higher Processor
        cursor, making every new RAW message look old and preventing an open
        session from ever appearing. This only advances SQLite's sequence; it does
        not rewrite existing messages or mutate RAW/Processor files.
        """

        safe_floor = max(0, int(floor))
        with self._lock, closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(id), 0) AS max_id FROM messages"
            ).fetchone()
            max_existing = int(row["max_id"] if row is not None else 0)
            target = max(safe_floor, max_existing)

            sequence = connection.execute(
                "SELECT seq FROM sqlite_sequence WHERE name = 'messages'"
            ).fetchone()
            current_sequence = int(sequence["seq"] if sequence is not None else 0)
            if current_sequence < target:
                if sequence is None:
                    connection.execute(
                        "INSERT INTO sqlite_sequence(name, seq) VALUES ('messages', ?)",
                        (target,),
                    )
                else:
                    connection.execute(
                        "UPDATE sqlite_sequence SET seq = ? WHERE name = 'messages'",
                        (target,),
                    )
                connection.commit()
            return max(target, current_sequence)

    def add(
        self,
        direction: str,
        text: str,
        resynchronized: bool = False,
        channel: str = "ooc",
    ) -> dict:
        timestamp = datetime.now(timezone.utc).isoformat()
        safe_channel = self._channel(channel)
        with self._lock, closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT INTO messages(timestamp, direction, channel, text, resynchronized)
                VALUES (?, ?, ?, ?, ?)
                """,
                (timestamp, direction, safe_channel, text, int(resynchronized)),
            )
            connection.commit()
            message_id = int(cursor.lastrowid)

        return {
            "id": message_id,
            "timestamp": timestamp,
            "direction": direction,
            "channel": safe_channel,
            "text": text,
            "resynchronized": bool(resynchronized),
        }

    def monitor_state(self) -> tuple[str | None, str]:
        with self._lock, closing(self._connect()) as connection, connection:
            rows = connection.execute(
                """
                SELECT key, value
                FROM runtime_state
                WHERE key IN ('chat_snapshot', 'channel_parser_pending')
                """
            ).fetchall()
        values = {str(row["key"]): str(row["value"]) for row in rows}
        return values.get("chat_snapshot"), values.get("channel_parser_pending", "")

    def save_monitor_state(self, snapshot: str, pending_text: str) -> None:
        with self._lock, closing(self._connect()) as connection, connection:
            connection.executemany(
                """
                INSERT INTO runtime_state(key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (
                    ("chat_snapshot", str(snapshot)),
                    ("channel_parser_pending", str(pending_text)),
                ),
            )
            connection.commit()

    def get_runtime_state(self, key: str, default: str = "") -> str:
        with self._lock, closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT value FROM runtime_state WHERE key = ?",
                (str(key),),
            ).fetchone()
        return str(row["value"]) if row is not None else str(default)

    def set_runtime_state(self, key: str, value: str) -> None:
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO runtime_state(key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(key), str(value)),
            )
            connection.commit()

    def incoming_after_id(self, after_id: int, limit: int = 2000) -> list[dict]:
        safe_after_id = max(0, int(after_id))
        safe_limit = max(1, min(int(limit), 5000))
        with self._lock, closing(self._connect()) as connection, connection:
            rows = connection.execute(
                """
                SELECT id, timestamp, direction, channel, text, resynchronized
                FROM messages
                WHERE direction = 'incoming' AND id > ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (safe_after_id, safe_limit),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "timestamp": str(row["timestamp"]),
                "direction": str(row["direction"]),
                "channel": self._channel(row["channel"]),
                "text": str(row["text"]),
                "resynchronized": bool(row["resynchronized"]),
            }
            for row in rows
        ]

    def recent_incoming_records(self, limit: int = 500) -> list[tuple[str, str]]:
        safe_limit = max(1, min(int(limit), 2000))
        with self._lock, closing(self._connect()) as connection, connection:
            rows = connection.execute(
                """
                SELECT channel, text
                FROM messages
                WHERE direction = 'incoming'
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [
            (self._channel(row["channel"]), str(row["text"]))
            for row in reversed(rows)
        ]

    def recent_incoming_texts(self, limit: int = 800) -> list[str]:
        safe_limit = max(1, min(int(limit), 2000))
        with self._lock, closing(self._connect()) as connection, connection:
            rows = connection.execute(
                """
                SELECT text
                FROM messages
                WHERE direction = 'incoming'
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [str(row["text"]) for row in reversed(rows)]

    def recent(self, limit: int = 500) -> list[dict]:
        safe_limit = max(1, min(int(limit), 2000))
        with self._lock, closing(self._connect()) as connection, connection:
            rows = connection.execute(
                """
                SELECT id, timestamp, direction, channel, text, resynchronized
                FROM messages
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

        return [
            {
                "id": int(row["id"]),
                "timestamp": row["timestamp"],
                "direction": row["direction"],
                "channel": self._channel(row["channel"]),
                "text": row["text"],
                "resynchronized": bool(row["resynchronized"]),
            }
            for row in reversed(rows)
        ]

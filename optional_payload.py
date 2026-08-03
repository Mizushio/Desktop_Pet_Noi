from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse


PRIVATE_CONFIG_FILENAME = "desktop_pet.private.json"

_CONTENT_KEYS = (
    "message",
    "msg",
    "content",
    "text",
    "chat_content",
    "msg_content",
    "message_content",
    "chat_msg",
)
_SENDER_KEYS = (
    "sender",
    "username",
    "user",
    "name",
    "account",
    "from",
    "role",
    "send_user",
    "from_user",
    "send_people",
    "chat_user",
)
_TIME_KEYS = (
    "timestamp",
    "created_at",
    "datetime",
    "time",
    "date",
    "send_time",
    "send_datetime",
    "create_time",
)
_ID_KEYS = ("id", "message_id", "msg_id", "chat_id", "uuid", "message_uuid")
_LIST_KEYS = ("messages", "message_list", "chat", "history", "data", "result")


def private_chat_config_path() -> Path:
    """Return the external private config beside source code or the EXE."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / PRIVATE_CONFIG_FILENAME
    return Path(__file__).resolve().parent / PRIVATE_CONFIG_FILENAME


@dataclass(frozen=True)
class ChatMonitorConfig:
    site_url: str
    api_url: str
    websocket_url: str
    password: str
    password_field: str
    websocket_auth_mode: str
    poll_interval_seconds: int
    reconnect_interval_seconds: int
    request_timeout_seconds: int
    popup_duration_seconds: int
    max_popup_messages: int
    max_message_characters: int

    @classmethod
    def load(cls, path: Path | None = None) -> "ChatMonitorConfig":
        config_path = private_chat_config_path() if path is None else path
        with config_path.open("r", encoding="utf-8") as file:
            raw = json.load(file)
        if not isinstance(raw, dict):
            raise ValueError("聊天配置的最外层必须是 JSON 对象")

        config = cls(
            site_url=str(raw.get("site_url", "")).strip(),
            api_url=str(raw.get("api_url", "")).strip(),
            websocket_url=str(raw.get("websocket_url", "")).strip(),
            password=str(raw.get("password", "")),
            password_field=str(raw.get("password_field", "psw")).strip(),
            websocket_auth_mode=str(
                raw.get("websocket_auth_mode", "query")
            ).strip(),
            poll_interval_seconds=int(raw.get("poll_interval_seconds", 20)),
            reconnect_interval_seconds=int(
                raw.get("reconnect_interval_seconds", 5)
            ),
            request_timeout_seconds=int(raw.get("request_timeout_seconds", 12)),
            popup_duration_seconds=int(raw.get("popup_duration_seconds", 18)),
            max_popup_messages=int(raw.get("max_popup_messages", 5)),
            max_message_characters=int(raw.get("max_message_characters", 500)),
        )
        config.validate()
        return config

    def validate(self) -> None:
        _require_url(self.site_url, {"http", "https"}, "site_url")
        _require_url(self.api_url, {"http", "https"}, "api_url")
        _require_url(self.websocket_url, {"ws", "wss"}, "websocket_url")
        if not self.password_field:
            raise ValueError("password_field 不能为空")
        if self.websocket_auth_mode not in {"none", "query", "json_message"}:
            raise ValueError(
                "websocket_auth_mode 只能是 none、query 或 json_message"
            )
        if not self.password:
            raise ValueError("password 不能为空")
        for name, value, minimum, maximum in (
            ("poll_interval_seconds", self.poll_interval_seconds, 3, 3600),
            (
                "reconnect_interval_seconds",
                self.reconnect_interval_seconds,
                2,
                300,
            ),
            ("request_timeout_seconds", self.request_timeout_seconds, 3, 120),
            ("popup_duration_seconds", self.popup_duration_seconds, 3, 300),
            ("max_popup_messages", self.max_popup_messages, 1, 20),
            ("max_message_characters", self.max_message_characters, 40, 5000),
        ):
            if not minimum <= value <= maximum:
                raise ValueError(f"{name} 必须在 {minimum}～{maximum} 之间")


def _require_url(value: str, schemes: set[str], name: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme.lower() not in schemes or not parsed.netloc:
        raise ValueError(f"{name} 不是有效地址")


@dataclass(frozen=True)
class MessageRecord:
    token_base: str
    content: str
    sender: str = ""
    timestamp: str = ""

    def display_text(self, max_characters: int) -> str:
        text = self.content.strip()
        if len(text) > max_characters:
            text = text[: max(1, max_characters - 1)].rstrip() + "…"
        header_parts = [part for part in (self.sender, self.timestamp) if part]
        if not header_parts:
            return text
        return f"{' · '.join(header_parts)}\n{text}"


def extract_message_records(payload: Any) -> list[MessageRecord]:
    """Normalize common chat API response shapes into displayable messages."""
    if isinstance(payload, Mapping) and payload.get("ok") is False:
        error = payload.get("error") or payload.get("message") or "API 返回失败"
        raise ValueError(str(error))

    candidates: list[tuple[int, int, Sequence[Any]]] = []
    _collect_message_lists(payload, candidates, depth=0)
    if not candidates:
        return []
    _, _, raw_messages = max(candidates, key=lambda item: (item[0], item[1]))

    records: list[MessageRecord] = []
    for raw_message in raw_messages:
        record = _normalize_message(raw_message)
        if record is not None:
            records.append(record)
    return records


def _collect_message_lists(
    value: Any,
    candidates: list[tuple[int, int, Sequence[Any]]],
    *,
    depth: int,
) -> None:
    if depth > 5:
        return
    if isinstance(value, Mapping):
        for key in _LIST_KEYS:
            child = value.get(key)
            if isinstance(child, Sequence) and not isinstance(
                child, (str, bytes, bytearray)
            ):
                score = sum(_message_shape_score(item) for item in child)
                candidates.append((score, len(child), child))
        for child in value.values():
            if isinstance(child, (Mapping, list, tuple)):
                _collect_message_lists(child, candidates, depth=depth + 1)
        return
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        score = sum(_message_shape_score(item) for item in value)
        candidates.append((score, len(value), value))
        for child in value:
            if isinstance(child, (Mapping, list, tuple)):
                _collect_message_lists(child, candidates, depth=depth + 1)


def _message_shape_score(value: Any) -> int:
    if isinstance(value, str):
        return 1
    if not isinstance(value, Mapping):
        return 0
    keys = {str(key).lower() for key in value}
    score = 0
    if keys.intersection(_CONTENT_KEYS):
        score += 8
    if keys.intersection(_SENDER_KEYS):
        score += 2
    if keys.intersection(_TIME_KEYS):
        score += 2
    if keys.intersection(_ID_KEYS):
        score += 2
    return score


def _normalize_message(value: Any) -> MessageRecord | None:
    if isinstance(value, str):
        content = value.strip()
        if not content:
            return None
        return MessageRecord(_fingerprint(("", "", content)), content)
    if not isinstance(value, Mapping):
        return None

    lowered = {str(key).lower(): item for key, item in value.items()}
    content = _first_text(lowered, _CONTENT_KEYS)
    if not content:
        return None
    sender = _first_text(lowered, _SENDER_KEYS)
    timestamp = _first_text(lowered, _TIME_KEYS)
    stable_id = _first_text(lowered, _ID_KEYS)
    if stable_id:
        token_base = "id:" + stable_id
    else:
        token_base = _fingerprint((sender, timestamp, content))
    return MessageRecord(token_base, content, sender, timestamp)


def _first_text(values: Mapping[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        if key not in values:
            continue
        text = _coerce_text(values[key])
        if text:
            return text
    return ""


def _coerce_text(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, (str, int, float)):
        return str(value).strip()
    if isinstance(value, Mapping):
        lowered = {str(key).lower(): item for key, item in value.items()}
        return _first_text(lowered, ("name", "username", "display_name", "value"))
    return ""


def _fingerprint(parts: tuple[str, str, str]) -> str:
    serialized = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return "fp:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class MessageSnapshotTracker:
    """Detect additions while treating the first successful snapshot as history."""

    def __init__(self, *, max_seen_tokens: int = 4096) -> None:
        self._initialized = False
        self._max_seen_tokens = max_seen_tokens
        self._seen_order: deque[str] = deque()
        self._seen: set[str] = set()

    @property
    def initialized(self) -> bool:
        return self._initialized

    def reset(self) -> None:
        self._initialized = False
        self._seen_order.clear()
        self._seen.clear()

    def ingest(self, records: Sequence[MessageRecord]) -> list[MessageRecord]:
        occurrence_counts: Counter[str] = Counter()
        tokenized: list[tuple[str, MessageRecord]] = []
        for record in records:
            occurrence_counts[record.token_base] += 1
            token = f"{record.token_base}#{occurrence_counts[record.token_base]}"
            tokenized.append((token, record))

        if not self._initialized:
            self._initialized = True
            for token, _ in tokenized:
                self._remember(token)
            return []

        new_records: list[MessageRecord] = []
        for token, record in tokenized:
            if token not in self._seen:
                new_records.append(record)
                self._remember(token)
        return new_records

    def _remember(self, token: str) -> None:
        if token in self._seen:
            return
        self._seen.add(token)
        self._seen_order.append(token)
        while len(self._seen_order) > self._max_seen_tokens:
            expired = self._seen_order.popleft()
            self._seen.discard(expired)

from __future__ import annotations

import json

from PySide6.QtCore import QByteArray, QObject, QTimer, QUrl, QUrlQuery, Signal
from PySide6.QtNetwork import (
    QAbstractSocket,
    QNetworkAccessManager,
    QNetworkReply,
    QNetworkRequest,
)
from PySide6.QtWebSockets import QWebSocket, QWebSocketProtocol

from optional_payload import (
    ChatMonitorConfig,
    MessageRecord,
    MessageSnapshotTracker,
    extract_message_records,
)


class ChatMonitor(QObject):
    """WebSocket-assisted API monitor with polling and deduplication."""

    new_messages = Signal(object)
    status_changed = Signal(str)

    def __init__(self, config: ChatMonitorConfig, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self._running = False
        self._request_in_flight = False
        self._refresh_queued = False
        self._tracker = MessageSnapshotTracker()
        self._network = QNetworkAccessManager(self)
        self._websocket = QWebSocket(
            "",
            QWebSocketProtocol.Version.VersionLatest,
            self,
        )

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(config.poll_interval_seconds * 1000)
        self._poll_timer.timeout.connect(self.refresh_now)

        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.setInterval(config.reconnect_interval_seconds * 1000)
        self._reconnect_timer.timeout.connect(self._connect_websocket)

        self._websocket.connected.connect(self._on_websocket_connected)
        self._websocket.disconnected.connect(self._on_websocket_disconnected)
        self._websocket.textMessageReceived.connect(
            lambda _message: self.refresh_now()
        )
        self._websocket.binaryMessageReceived.connect(
            lambda _message: self.refresh_now()
        )
        error_signal = getattr(self._websocket, "errorOccurred", None)
        if error_signal is not None:
            error_signal.connect(self._on_websocket_error)

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._tracker.reset()
        self._poll_timer.start()
        self.status_changed.emit("正在同步")
        self.refresh_now()
        self._connect_websocket()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._poll_timer.stop()
        self._reconnect_timer.stop()
        self._websocket.close()
        self.status_changed.emit("已关闭")

    def refresh_now(self) -> None:
        if not self._running:
            return
        if self._request_in_flight:
            self._refresh_queued = True
            return

        request = QNetworkRequest(QUrl(self.config.api_url))
        request.setHeader(
            QNetworkRequest.KnownHeaders.ContentTypeHeader,
            "application/json; charset=utf-8",
        )
        request.setRawHeader(QByteArray(b"Accept"), QByteArray(b"application/json"))
        set_timeout = getattr(request, "setTransferTimeout", None)
        if set_timeout is not None:
            set_timeout(self.config.request_timeout_seconds * 1000)

        payload = json.dumps(
            {self.config.password_field: self.config.password},
            ensure_ascii=False,
        ).encode("utf-8")
        self._request_in_flight = True
        reply = self._network.post(request, QByteArray(payload))
        reply.finished.connect(lambda current=reply: self._finish_request(current))

    def _finish_request(self, reply: QNetworkReply) -> None:
        self._request_in_flight = False
        try:
            raw_data = bytes(reply.readAll())
            if not self._running:
                return
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.status_changed.emit("API 暂时不可用，等待重试")
                return
            payload = json.loads(raw_data.decode("utf-8-sig"))
            records = extract_message_records(payload)
            new_records = self._tracker.ingest(records)
            if new_records:
                self.new_messages.emit(new_records)
            if self._websocket.state() == QAbstractSocket.SocketState.ConnectedState:
                self.status_changed.emit("实时连接正常")
            else:
                self.status_changed.emit("API 轮询正常")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
            self.status_changed.emit("API 返回格式无法识别")
        finally:
            reply.deleteLater()
            if self._refresh_queued and self._running:
                self._refresh_queued = False
                QTimer.singleShot(0, self.refresh_now)

    def _connect_websocket(self) -> None:
        if not self._running:
            return
        state = self._websocket.state()
        if state in {
            QAbstractSocket.SocketState.ConnectedState,
            QAbstractSocket.SocketState.ConnectingState,
        }:
            return

        url = QUrl(self.config.websocket_url)
        if self.config.websocket_auth_mode == "query":
            query = QUrlQuery(url)
            query.removeAllQueryItems(self.config.password_field)
            query.addQueryItem(self.config.password_field, self.config.password)
            url.setQuery(query)
        self._websocket.open(url)

    def _on_websocket_connected(self) -> None:
        self._reconnect_timer.stop()
        if self.config.websocket_auth_mode == "json_message":
            payload = json.dumps(
                {self.config.password_field: self.config.password},
                ensure_ascii=False,
            )
            self._websocket.sendTextMessage(payload)
        self.status_changed.emit("实时连接正常")
        self.refresh_now()

    def _on_websocket_disconnected(self) -> None:
        if not self._running:
            return
        self.status_changed.emit("实时连接断开，API 轮询中")
        if not self._reconnect_timer.isActive():
            self._reconnect_timer.start()

    def _on_websocket_error(self, _error: object) -> None:
        if not self._running:
            return
        self.status_changed.emit("实时连接异常，API 轮询中")
        if not self._reconnect_timer.isActive():
            self._reconnect_timer.start()

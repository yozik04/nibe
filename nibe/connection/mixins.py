from enum import Enum


class ConnectionStatus(Enum):
    """Connection status of the NibeGW connection."""

    UNKNOWN = "unknown"
    INITIALIZING = "initializing"
    LISTENING = "listening"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"

    def __str__(self):
        return self.value


class ConnectionStatusMixin:
    CONNECTION_STATUS_EVENT = "connection_status"
    _status: ConnectionStatus = ConnectionStatus.UNKNOWN

    @property
    def status(self) -> ConnectionStatus:
        """Get the current connection status"""
        return self._status

    @status.setter
    def status(self, status: ConnectionStatus):
        if status != self._status:
            self._status = status
            self.notify_event_listeners(self.CONNECTION_STATUS_EVENT, status=status)

    def notify_event_listeners(self, *args, **kwargs):
        pass

"""Transport seam for talking to a ChefsTemp stand.

The wire frames are identical over the cloud MQTT channel and over local BLE, so
the rest of the integration is written against this interface and does not care
which one is in use. Only the cloud transport (mqtt.py) is implemented today; a
BLE transport can be added behind the same interface later (the stand's GATT
read/write is proven — see docs/PROTOCOL.md §4b — but needs a BLE adapter HA can
reach, which this project's ESP32 proxy currently cannot provide).

Callbacks fire on the transport's own thread; the caller is responsible for
hopping onto the event loop.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable


class ChefsTempTransport(ABC):
    """A bidirectional frame channel to one stand."""

    def __init__(
        self,
        on_frame: Callable[[bytes], None],
        on_connect_change: Callable[[bool], None] | None = None,
    ) -> None:
        """Store the callbacks; no I/O happens until connect()."""
        self._on_frame = on_frame
        self._on_connect_change = on_connect_change

    @property
    @abstractmethod
    def connected(self) -> bool:
        """Whether the channel is currently up."""

    @abstractmethod
    def connect(self) -> None:
        """Open the channel (may block; call from an executor)."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the channel (may block; call from an executor)."""

    @abstractmethod
    def send(self, frame: bytes) -> None:
        """Send one command frame (may block; call from an executor)."""

"""The Bluetooth seam: a thin `BluetoothController` so the app/tuner never touch
D-Bus directly.

`FakeBluetoothController` is an in-memory implementation for tests (runs anywhere).
`DbusBluetoothController` (in `dbus.py`) drives the real BlueZ stack and lazy-imports
`dbus-fast`, so importing this module on the Mac costs nothing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BluetoothController(ABC):
    @abstractmethod
    async def start(self) -> None:
        """Power on the adapter and register the pairing agent."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop discovery, unregister the agent, release the bus — safe twice."""

    @abstractmethod
    async def start_discovery(self) -> None: ...

    @abstractmethod
    async def stop_discovery(self) -> None: ...

    @abstractmethod
    async def pair(self, mac: str) -> None: ...

    @abstractmethod
    async def connect(self, mac: str) -> None: ...

    @abstractmethod
    async def disconnect(self, mac: str) -> None: ...

    @abstractmethod
    async def forget(self, mac: str) -> None: ...

    @abstractmethod
    def state(self) -> dict:
        """Snapshot folded into build_state:
        {enabled, scanning, devices:[{mac,name,paired,connected}], connected}."""

    def set_on_change(self, cb) -> None:
        """Register a no-arg callback invoked on any device/adapter change."""
        self._on_change = cb

    def _notify(self) -> None:
        cb = getattr(self, "_on_change", None)
        if cb is not None:
            cb()


class FakeBluetoothController(BluetoothController):
    """In-memory controller for tests. `seed` is a list of device dicts
    `{mac, name, paired, connected}`; `discoverable` are devices that only appear
    after `start_discovery()` (simulating a scan finding a speaker)."""

    def __init__(self, seed=None, discoverable=None):
        self._devices = {d["mac"]: dict(d) for d in (seed or [])}
        self._pending = {d["mac"]: dict(d) for d in (discoverable or [])}
        self.scanning = False
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True
        self.scanning = False

    async def start_discovery(self) -> None:
        self.scanning = True
        # Discovery surfaces the "nearby" devices.
        for mac, d in self._pending.items():
            self._devices.setdefault(mac, dict(d))
        self._notify()

    async def stop_discovery(self) -> None:
        self.scanning = False
        self._notify()

    def _dev(self, mac: str) -> dict:
        if mac not in self._devices:
            raise KeyError(f"unknown device {mac}")
        return self._devices[mac]

    async def pair(self, mac: str) -> None:
        self._dev(mac)["paired"] = True
        self._notify()

    async def connect(self, mac: str) -> None:
        d = self._dev(mac)
        d["paired"] = True
        # one connected device at a time
        for other in self._devices.values():
            other["connected"] = False
        d["connected"] = True
        self._notify()

    async def disconnect(self, mac: str) -> None:
        self._dev(mac)["connected"] = False
        self._notify()

    async def forget(self, mac: str) -> None:
        self._devices.pop(mac, None)
        self._notify()

    def state(self) -> dict:
        devices = [
            {"mac": m, "name": d.get("name", m), "paired": bool(d.get("paired")),
             "connected": bool(d.get("connected"))}
            for m, d in self._devices.items()
        ]
        connected = next((d["mac"] for d in devices if d["connected"]), None)
        return {"enabled": True, "scanning": self.scanning,
                "devices": devices, "connected": connected}

    # test helper: simulate an unsolicited drop (e.g. speaker powered off)
    def simulate_drop(self, mac: str) -> None:
        if mac in self._devices:
            self._devices[mac]["connected"] = False
            self._notify()

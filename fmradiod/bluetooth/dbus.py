"""The real BlueZ controller over the system bus via `dbus-fast`.

This is the hardware/bus-touching seam — NOT unit-tested on the Mac (no system
bus); exercised on the Pi (group 7). Everything is lazy: `dbus-fast` is imported
inside `start()`, so importing this module on the Mac is free. Construction +
`start()` raising is fine — the caller (lifespan) turns any failure into fail-soft
web-only operation.

BlueZ object model used here:
- adapter `org.bluez.Adapter1` at `/org/bluez/<hciX>` (Powered, StartDiscovery,
  StopDiscovery, RemoveDevice)
- devices `org.bluez.Device1` at `…/dev_AA_BB_…` (Pair, Connect, Disconnect,
  Name/Alias, Address, Paired, Connected)
- `org.freedesktop.DBus.ObjectManager` at `/` for the device list + add/remove signals
- a `NoInputNoOutput` `org.bluez.Agent1` registered with `org.bluez.AgentManager1`
  for just-works pairing
"""

from __future__ import annotations

import logging

from fmradiod.bluetooth.controller import BluetoothController

log = logging.getLogger("fmradiod.bluetooth")

_BLUEZ = "org.bluez"
_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
_ADAPTER_IFACE = "org.bluez.Adapter1"
_DEVICE_IFACE = "org.bluez.Device1"
_AGENT_IFACE = "org.bluez.Agent1"
_AGENT_MGR_IFACE = "org.bluez.AgentManager1"
_AGENT_PATH = "/fmradiod/agent"


def _dev_path(adapter_path: str, mac: str) -> str:
    return f"{adapter_path}/dev_" + mac.upper().replace(":", "_")


def _mac_from_path(path: str) -> str | None:
    tail = path.rsplit("/dev_", 1)
    if len(tail) != 2:
        return None
    return tail[1].replace("_", ":")


class DbusBluetoothController(BluetoothController):
    def __init__(self, adapter: str = "hci0"):
        self._adapter_name = adapter
        self._adapter_path = f"/org/bluez/{adapter}"
        self._bus = None
        self._adapter = None        # Adapter1 proxy interface
        self._om = None             # ObjectManager proxy interface
        self._agent = None
        self._scanning = False
        self._devices: dict[str, dict] = {}   # mac -> {name, paired, connected}
        self._subscribed: set[str] = set()     # device paths with PropertiesChanged wired

    # ----- lifecycle -----
    async def start(self) -> None:
        from dbus_fast import BusType
        from dbus_fast.aio import MessageBus

        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        self._adapter = await self._iface(self._adapter_path, _ADAPTER_IFACE)
        try:
            await self._adapter.set_powered(True)
        except Exception:
            log.warning("could not power on the bluetooth adapter", exc_info=True)

        await self._register_agent()

        # ObjectManager: initial device list + add/remove signals.
        self._om = await self._iface("/", _OM_IFACE)
        try:
            self._om.on_interfaces_added(lambda path, ifaces: self._schedule_refresh())
            self._om.on_interfaces_removed(lambda path, ifaces: self._schedule_refresh())
        except Exception:
            log.warning("could not subscribe to ObjectManager signals", exc_info=True)
        await self._refresh()

    async def stop(self) -> None:
        try:
            if self._scanning and self._adapter is not None:
                await self._adapter.call_stop_discovery()
        except Exception:
            pass
        try:
            if self._bus is not None and self._agent is not None:
                mgr = await self._iface("/org/bluez", _AGENT_MGR_IFACE)
                await mgr.call_unregister_agent(_AGENT_PATH)
        except Exception:
            pass
        try:
            if self._bus is not None:
                self._bus.disconnect()
        except Exception:
            pass
        self._bus = self._adapter = self._om = None

    # ----- discovery -----
    async def start_discovery(self) -> None:
        await self._adapter.call_start_discovery()
        self._scanning = True
        self._notify()

    async def stop_discovery(self) -> None:
        try:
            await self._adapter.call_stop_discovery()
        finally:
            self._scanning = False
            self._notify()

    # ----- per-device operations -----
    async def pair(self, mac: str) -> None:
        dev = await self._device(mac)
        await dev.call_pair()
        try:
            await dev.set_trusted(True)
        except Exception:
            pass
        await self._refresh()

    async def connect(self, mac: str) -> None:
        dev = await self._device(mac)
        try:
            await dev.set_trusted(True)
        except Exception:
            pass
        try:
            await dev.call_connect()
        except Exception:
            # BlueZ raises "Already Connected" for an auto-reconnected speaker —
            # not an error for us. Refresh so the cache reflects reality regardless.
            log.warning("connect(%s) raised (may already be connected)", mac, exc_info=True)
        await self._refresh()

    async def disconnect(self, mac: str) -> None:
        dev = await self._device(mac)
        await dev.call_disconnect()
        await self._refresh()

    async def forget(self, mac: str) -> None:
        try:
            await self._adapter.call_remove_device(_dev_path(self._adapter_path, mac))
        finally:
            self._devices.pop(mac, None)
            await self._refresh()

    # ----- state -----
    def state(self) -> dict:
        devices = [
            {"mac": m, "name": d.get("name", m), "paired": bool(d.get("paired")),
             "connected": bool(d.get("connected"))}
            for m, d in self._devices.items()
        ]
        connected = next((d["mac"] for d in devices if d["connected"]), None)
        return {"enabled": True, "scanning": self._scanning,
                "devices": devices, "connected": connected}

    # ----- internals -----
    async def _iface(self, path: str, iface: str):
        intro = await self._bus.introspect(_BLUEZ, path)
        obj = self._bus.get_proxy_object(_BLUEZ, path, intro)
        return obj.get_interface(iface)

    async def _device(self, mac: str):
        return await self._iface(_dev_path(self._adapter_path, mac), _DEVICE_IFACE)

    async def _register_agent(self) -> None:
        from dbus_fast.service import ServiceInterface, method

        class _Agent(ServiceInterface):
            def __init__(self):
                super().__init__(_AGENT_IFACE)

            @method()
            def Release(self):  # noqa: N802
                pass

            @method()
            def RequestConfirmation(self, device: "o", passkey: "u"):  # noqa: N802,F821
                pass  # just-works: auto-confirm

            @method()
            def RequestAuthorization(self, device: "o"):  # noqa: N802,F821
                pass

            @method()
            def AuthorizeService(self, device: "o", uuid: "s"):  # noqa: N802,F821
                pass

            @method()
            def Cancel(self):  # noqa: N802
                pass

            @method()
            def RequestPinCode(self, device: "o") -> "s":  # noqa: N802,F821
                return "0000"

            @method()
            def RequestPasskey(self, device: "o") -> "u":  # noqa: N802,F821
                return 0

            @method()
            def DisplayPinCode(self, device: "o", pincode: "s"):  # noqa: N802,F821
                pass

            @method()
            def DisplayPasskey(self, device: "o", passkey: "u", entered: "q"):  # noqa: N802,F821
                pass

        try:
            self._agent = _Agent()
            self._bus.export(_AGENT_PATH, self._agent)
            mgr = await self._iface("/org/bluez", _AGENT_MGR_IFACE)
            await mgr.call_register_agent(_AGENT_PATH, "NoInputNoOutput")
            await mgr.call_request_default_agent(_AGENT_PATH)
        except Exception:
            log.warning("could not register the bluetooth pairing agent", exc_info=True)

    def _schedule_refresh(self) -> None:
        import asyncio
        try:
            asyncio.ensure_future(self._refresh())
        except RuntimeError:
            pass

    async def _refresh(self) -> None:
        """Rebuild the device cache from BlueZ's managed objects."""
        try:
            objs = await self._om.call_get_managed_objects()
        except Exception:
            log.warning("bluetooth GetManagedObjects failed", exc_info=True)
            return
        devices: dict[str, dict] = {}
        for path, ifaces in objs.items():
            d = ifaces.get(_DEVICE_IFACE)
            if d is None or not path.startswith(self._adapter_path):
                continue
            mac = _mac_from_path(path)
            if not mac:
                continue
            name = d.get("Alias") or d.get("Name")
            devices[mac] = {
                "name": name.value if name is not None else mac,
                "paired": bool(d["Paired"].value) if "Paired" in d else False,
                "connected": bool(d["Connected"].value) if "Connected" in d else False,
            }
            await self._watch_device(path)
        self._devices = devices
        self._notify()

    async def _watch_device(self, path: str) -> None:
        """Subscribe to a device's PropertiesChanged so an unsolicited connect/
        disconnect (e.g. speaker powered off) updates our cache."""
        if path in self._subscribed:
            return
        try:
            props = await self._iface(path, "org.freedesktop.DBus.Properties")
            props.on_properties_changed(
                lambda iface, changed, inval: self._schedule_refresh()
                if iface == _DEVICE_IFACE else None
            )
            self._subscribed.add(path)
        except Exception:
            pass


def create_controller(adapter: str = "hci0") -> BluetoothController:
    """Construct the real BlueZ controller. Raises if `dbus-fast`/the bus is
    unavailable — the caller turns that into fail-soft web-only operation."""
    return DbusBluetoothController(adapter=adapter)

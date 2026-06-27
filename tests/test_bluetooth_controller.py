from fmradiod.bluetooth.controller import FakeBluetoothController


def _changes(c):
    seen = {"n": 0}
    c.set_on_change(lambda: seen.__setitem__("n", seen["n"] + 1))
    return seen


async def test_scan_surfaces_discoverable_devices():
    c = FakeBluetoothController(discoverable=[{"mac": "AA:1", "name": "Echo", "paired": False, "connected": False}])
    seen = _changes(c)
    assert c.state()["devices"] == []
    await c.start_discovery()
    assert c.state()["scanning"] is True
    macs = [d["mac"] for d in c.state()["devices"]]
    assert "AA:1" in macs
    assert seen["n"] >= 1


async def test_pair_then_connect_then_disconnect():
    c = FakeBluetoothController(seed=[{"mac": "AA:1", "name": "Echo", "paired": False, "connected": False}])
    await c.pair("AA:1")
    assert c.state()["devices"][0]["paired"] is True
    await c.connect("AA:1")
    st = c.state()
    assert st["connected"] == "AA:1"
    assert st["devices"][0]["connected"] is True
    await c.disconnect("AA:1")
    assert c.state()["connected"] is None


async def test_connect_is_exclusive():
    c = FakeBluetoothController(seed=[
        {"mac": "AA:1", "name": "Echo", "paired": True, "connected": True},
        {"mac": "BB:2", "name": "JBL", "paired": True, "connected": False},
    ])
    await c.connect("BB:2")
    st = c.state()
    assert st["connected"] == "BB:2"
    assert sum(1 for d in st["devices"] if d["connected"]) == 1


async def test_forget_removes_device():
    c = FakeBluetoothController(seed=[{"mac": "AA:1", "name": "Echo", "paired": True, "connected": False}])
    await c.forget("AA:1")
    assert c.state()["devices"] == []


async def test_simulated_drop_clears_connected_and_notifies():
    c = FakeBluetoothController(seed=[{"mac": "AA:1", "name": "Echo", "paired": True, "connected": True}])
    seen = _changes(c)
    c.simulate_drop("AA:1")
    assert c.state()["connected"] is None
    assert seen["n"] == 1


def test_dbus_module_imports_without_a_bus():
    # Importing the real controller module must not require dbus-fast or a bus
    # (the import is lazy inside start()); construction is also lazy-free.
    from fmradiod.bluetooth.dbus import DbusBluetoothController, _dev_path, _mac_from_path
    c = DbusBluetoothController(adapter="hci0")
    assert c.state() == {"enabled": True, "scanning": False, "devices": [], "connected": None}
    assert _dev_path("/org/bluez/hci0", "50:99:5A:21:F8:BB") == "/org/bluez/hci0/dev_50_99_5A_21_F8_BB"
    assert _mac_from_path("/org/bluez/hci0/dev_50_99_5A_21_F8_BB") == "50:99:5A:21:F8:BB"

import asyncio

from fmradiod.audio import FanOut


class FakeReader:
    """Stand-in for an asyncio StreamReader (e.g. ffmpeg stdout)."""

    def __init__(self, chunks):
        self._chunks = list(chunks)

    async def read(self, n):
        return self._chunks.pop(0) if self._chunks else b""


async def test_two_clients_both_receive():
    fo = FanOut(maxsize=8)
    a = fo.register()
    b = fo.register()
    fo.broadcast(b"x")
    assert await asyncio.wait_for(a.queue.get(), 1) == b"x"
    assert await asyncio.wait_for(b.queue.get(), 1) == b"x"


async def test_register_unregister_counts():
    fo = FanOut()
    c = fo.register()
    assert fo.client_count == 1
    fo.unregister(c)
    assert fo.client_count == 0


async def test_slow_client_drops_oldest_without_blocking_fast():
    fo = FanOut(maxsize=2)
    slow = fo.register()
    fast = fo.register()
    received_fast = []
    for i in range(5):
        fo.broadcast(bytes([i]))
        received_fast.append(fast.queue.get_nowait())  # fast drains immediately
    assert received_fast == [bytes([i]) for i in range(5)]  # fast got everything
    assert slow.queue.qsize() == 2                          # slow capped at maxsize
    assert slow.dropped == 3
    assert slow.queue.get_nowait() == bytes([3])            # only the two newest survive
    assert slow.queue.get_nowait() == bytes([4])


async def test_stream_generator_registers_and_unregisters():
    fo = FanOut(maxsize=4)
    gen = fo.stream()
    task = asyncio.ensure_future(gen.__anext__())  # starting it registers the client
    await asyncio.sleep(0.01)
    assert fo.client_count == 1
    fo.broadcast(b"hello")
    assert await asyncio.wait_for(task, 1) == b"hello"
    await gen.aclose()
    assert fo.client_count == 0


async def test_pump_reads_until_eof_and_broadcasts():
    fo = FanOut(maxsize=16)
    c = fo.register()
    await fo.pump(FakeReader([b"a", b"b", b"c"]))
    got = [c.queue.get_nowait() for _ in range(c.queue.qsize())]
    assert got == [b"a", b"b", b"c"]


async def test_pump_calls_on_first_once():
    fo = FanOut(maxsize=16)
    calls = []
    await fo.pump(FakeReader([b"a", b"b", b"c"]), on_first=lambda: calls.append(1))
    assert calls == [1]  # fired exactly once, on the first chunk


async def test_source_swap_continues_delivery():
    fo = FanOut(maxsize=16)
    c = fo.register()  # one long-lived client across two sources
    await fo.pump(FakeReader([b"old1", b"old2"]))
    await fo.pump(FakeReader([b"new1", b"new2"]))
    got = [c.queue.get_nowait() for _ in range(c.queue.qsize())]
    assert got == [b"old1", b"old2", b"new1", b"new2"]

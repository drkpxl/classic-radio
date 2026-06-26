import asyncio

from fmradiod.events import EventBus


async def test_subscriber_receives_published_event():
    bus = EventBus()
    q = bus.subscribe()
    bus.publish({"type": "state", "preset": 1})
    assert await asyncio.wait_for(q.get(), 1) == {"type": "state", "preset": 1}


async def test_multiple_subscribers_all_receive():
    bus = EventBus()
    q1 = bus.subscribe()
    q2 = bus.subscribe()
    bus.publish("hello")
    assert await asyncio.wait_for(q1.get(), 1) == "hello"
    assert await asyncio.wait_for(q2.get(), 1) == "hello"


async def test_unsubscribe_stops_delivery():
    bus = EventBus()
    q = bus.subscribe()
    assert bus.subscriber_count == 1
    bus.unsubscribe(q)
    assert bus.subscriber_count == 0
    bus.publish("x")  # no subscribers; must not raise
    assert q.empty()


async def test_events_generator_yields_and_cleans_up():
    bus = EventBus()
    gen = bus.events()
    task = asyncio.ensure_future(gen.__anext__())  # starting registers
    await asyncio.sleep(0.01)
    assert bus.subscriber_count == 1
    bus.publish("ev")
    assert await asyncio.wait_for(task, 1) == "ev"
    await gen.aclose()
    assert bus.subscriber_count == 0

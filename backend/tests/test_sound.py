import asyncio

from app import sound


def test_alarm_stop_and_voice_are_sent_to_the_board(monkeypatch):
    sent = []

    async def fake(path, params, body):
        sent.append((path, params, body))

    async def scenario():
        monkeypatch.setattr(sound, "senders", [fake])
        sound.alarm()
        sound.prepare_voice("Bonjour Léa")
        sound.stop()
        await asyncio.sleep(0)
        await asyncio.gather(*list(sound._tasks))

    asyncio.run(scenario())
    assert ("/sound/alarm", {"seconds": sound.ALARM_SECONDS}, None) in sent
    assert ("/audio/voice/prepare", None, {"texts": ["Bonjour Léa"]}) in sent
    assert ("/sound/stop", None, None) in sent


def test_unreachable_board_does_not_raise(monkeypatch):
    async def broken(path, params, body):
        raise OSError("talos injoignable")

    async def scenario():
        monkeypatch.setattr(sound, "senders", [broken])
        sound.alarm()
        await asyncio.sleep(0)
        await asyncio.gather(*list(sound._tasks))

    asyncio.run(scenario())  # journalisé, jamais propagé


def test_alarm_state_follows_start_and_stop(monkeypatch):
    from app import sound
    sent = []
    monkeypatch.setattr(sound, "_background", lambda path, params=None, body=None: sent.append(path))
    sound.stop()  # un test précédent a pu laisser l'alarme en cours
    sent.clear()
    assert not sound.alarm_active()
    sound.alarm(60)
    assert sound.alarm_active()
    sound.hello("Léa")
    sound.stop()
    assert not sound.alarm_active()
    assert sent == ["/sound/alarm", "/sound/hello", "/sound/stop"]

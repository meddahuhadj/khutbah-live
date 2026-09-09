"""live_translate.py — session Gemini Live (WebSocket mockée, aucun appel réseau)."""
import asyncio
import json

import pytest

import live_translate


# --------------------------------------------------------------------------- #
# Faux WebSocket : enregistre les messages clients, émet les messages serveur.
# --------------------------------------------------------------------------- #
class FakeWS:
    def __init__(self, server_msgs=None):
        self.server_msgs = list(server_msgs) if server_msgs is not None else []
        self.sent = []            # messages JSON envoyés par le client
        self.closed = False

    async def send(self, raw):
        self.sent.append(raw)

    async def close(self):
        self.closed = True

    def push(self, msg):
        self.server_msgs.append(msg)

    def __aiter__(self):
        return self

    async def __anext__(self):
        while not self.server_msgs:
            if self.closed:
                raise StopAsyncIteration
            await asyncio.sleep(0.01)
        return json.dumps(self.server_msgs.pop(0))


def _use(monkeypatch, fake_ws, **cfg):
    """Branche `_connect` sur le FakeWS et applique la config de test."""
    async def _c(url, **kw):
        return fake_ws
    monkeypatch.setattr(live_translate, "_connect", _c)
    monkeypatch.setattr(live_translate, "LIVE_CONNECT_RETRIES", 0)
    monkeypatch.setattr(live_translate, "LIVE_SETUP_TMO", 2.0)
    for k, v in cfg.items():
        monkeypatch.setattr(live_translate, k, v)
    return fake_ws


_SENTINEL = object()


class _Coll:
    """Récepteur : collecte les événements pour l'assertion."""
    def __init__(self):
        self.events = []

    def __call__(self, ev):
        self.events.append(ev)


@pytest.fixture(autouse=True)
async def _await_tasks():
    yield
    for t in list(asyncio.all_tasks()):
        if t is not asyncio.current_task() and not t.done():
            t.cancel()
    await asyncio.sleep(0)


async def test_setup_message_is_sent(monkeypatch):
    coll = _Coll()
    fake = _use(monkeypatch, FakeWS([{"setupComplete": {}}]),
                LIVE_MODEL="m-model-test")
    sess = live_translate.LiveTranslateSession("k1", "fr", coll,
                                                model="m-model-test")
    assert await sess.start() is True
    assert len(fake.sent) == 1
    setup = json.loads(fake.sent[0])["setup"]
    assert setup["model"] == "models/m-model-test"
    gc = setup["generationConfig"]
    assert gc["translationConfig"]["targetLanguageCode"] == "fr"
    assert gc["translationConfig"]["echoTargetLanguage"] is False
    assert gc["responseModalities"] == ["AUDIO"]
    # transcripts d'entrée/sortie demandés au niveau setup (pas generationConfig)
    assert "inputAudioTranscription" in setup
    assert "outputAudioTranscription" in setup
    await sess.stop()


async def test_start_fails_when_timeout(monkeypatch):
    coll = _Coll()
    _use(monkeypatch, FakeWS(), LIVE_SETUP_TMO=0.2)
    sess = live_translate.LiveTranslateSession("k1", "fr", coll)
    assert await sess.start() is False
    assert {"type": "error", "reason": "live_no_session"} in coll.events
    await sess.stop()


async def test_start_fails_on_connect_error(monkeypatch):
    coll = _Coll()

    async def _boom(url, **kw):
        raise OSError("connexion refusée")

    monkeypatch.setattr(live_translate, "_connect", _boom)
    monkeypatch.setattr(live_translate, "LIVE_CONNECT_RETRIES", 1)
    sess = live_translate.LiveTranslateSession("k1", "fr", coll)
    assert await sess.start() is False
    assert coll.events and coll.events[-1]["type"] == "error"
    assert coll.events[-1]["reason"] == "live_no_session"


async def test_send_audio_relays_pcm_base64(monkeypatch):
    coll = _Coll()
    fake = _use(monkeypatch, FakeWS([{"setupComplete": {}}]))
    sess = live_translate.LiveTranslateSession("k1", "fr", coll)
    assert await sess.start() is True
    await sess.send_audio(b"\x00\x01\x02\x03" * 400)
    assert len(fake.sent) == 2
    real = json.loads(fake.sent[1])["realtimeInput"]["audio"]
    assert real["mimeType"] == "audio/pcm;rate=16000"
    import base64
    assert base64.b64decode(real["data"]) == b"\x00\x01\x02\x03" * 400
    await sess.stop()


async def test_receives_transcript_and_translation(monkeypatch):
    coll = _Coll()
    _use(monkeypatch, FakeWS([
        {"setupComplete": {}},
        {"serverContent": {
            "inputTranscription": {"text": "بسم الله الرحمن الرحيم"},
        }},
        {"serverContent": {
            "outputTranscription": {"text": "Au nom d'Allah"},
            "modelTurn": {"parts": [{"text": "Au nom d'Allah"}]},
        }},
    ]))
    sess = live_translate.LiveTranslateSession("k1", "fr", coll)
    assert await sess.start() is True
    await asyncio.sleep(0.05)
    types = [e["type"] for e in coll.events]
    assert "transcript" in types
    assert "translation" in types
    tr = next(e for e in coll.events if e["type"] == "transcript")
    assert tr["text"] == "بسم الله الرحمن الرحيم"
    await sess.stop()


async def test_ignores_unknown_messages(monkeypatch):
    coll = _Coll()
    _use(monkeypatch, FakeWS([
        {"setupComplete": {}},
        {"goAway": {"reason": "runtime_down"}},
        {"usageMetadata": {}},
    ]))
    sess = live_translate.LiveTranslateSession("k1", "fr", coll)
    assert await sess.start() is True
    await asyncio.sleep(0.05)
    assert not [e for e in coll.events if e["type"] in ("transcript", "translation")]
    await sess.stop()


async def test_audio_ignored_before_ready(monkeypatch):
    coll = _Coll()
    fake = _use(monkeypatch, FakeWS([{"setupComplete": {}}]))
    sess = live_translate.LiveTranslateSession("k1", "fr", coll)
    # avant start(): pas de session, send_audio -> False
    assert await sess.send_audio(b"x") is False
    assert await sess.start() is True
    assert await sess.send_audio(b"x" * 100) is True
    assert len(fake.sent) == 2
    await sess.stop()
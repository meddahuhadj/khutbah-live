"""Room fixe de la mosquée : même code tous les vendredis, pas de rescan du QR."""
import json

import main
from main import Room


def test_get_main_room_fixed_code():
    code = main.get_main_room().code
    assert code == main.MAIN_ROOM_CODE
    assert main.get_main_room() is main.ROOMS[main.MAIN_ROOM_CODE]


def test_purge_never_removes_main_room(monkeypatch):
    main.ROOMS.clear()
    main.get_main_room()
    # Une room éphémère purgée, la room fixe jamais.
    r = Room("ABC123")
    r.created_at = 0
    r.last_activity = 0
    main.ROOMS["ABC123"] = r
    monkeypatch.setattr(main, "IDLE_ROOM_TTL", 1)
    monkeypatch.setattr(main, "SESSION_TTL", 1)
    removed = main._purge_stale(now=9999)
    assert removed == 1
    assert main.MAIN_ROOM_CODE in main.ROOMS


def test_fixed_session_returns_stable_code_and_resets(app_client):
    main.ROOMS.clear()
    d1 = app_client.post("/api/session",
                         json={"fixed": True, "mosque_name": "Al-Furqan",
                               "target_langs": ["fr", "en"]}).json()
    assert d1["fixed"] is True
    assert d1["code"] == main.MAIN_ROOM_CODE

    with app_client.websocket_connect(
            f"/ws/broadcast/{d1['code']}?token={d1['broadcaster_token']}") as b:
        msg = json.loads(b.receive_text())
        assert msg["type"] == "hello"

    # Un second « démarrage » du vendredi suivant : même code, historique à zéro.
    d2 = app_client.post("/api/session",
                         json={"fixed": True, "target_langs": ["fr"]}).json()
    assert d2["code"] == d1["code"]
    room = main.get_room(d2["code"])
    assert room.seq == 0
    assert room.status == "idle"
    assert room.broadcaster is None
    assert len(room.history) == 0


def test_existing_session_unaffected(app_client):
    """Sans `fixed`, on garde les sessions à code aléatoire (rétrocompat)."""
    d = app_client.post("/api/session", json={}).json()
    assert d["fixed"] is False
    assert d["code"] != main.MAIN_ROOM_CODE
    assert len(d["code"]) == 6


def test_api_main_reports_status(app_client):
    main.ROOMS.clear()
    d = app_client.get("/api/main").json()
    assert d["code"] == main.MAIN_ROOM_CODE
    assert d["live"] is False
    assert "status" in d
    assert "mosque_name" in d


def test_listener_websocket_times_out_when_idle(app_client, monkeypatch):
    """WS_IDLE_TTL écoule les connexions inactives (connexion libérée)."""
    import time

    monkeypatch.setattr(main, "WS_IDLE_TTL", 0.1)
    sess = app_client.post("/api/session", json={"fixed": True}).json()

    with app_client.websocket_connect(f"/ws/listen/{sess['code']}") as l:
        hello = json.loads(l.receive_text())
        assert hello["type"] == "hello"
        time.sleep(0.4)
        # La fermeture côté serveur doit être perçue côté client.
        closed = False
        try:
            l.receive_text()
        except Exception:
            closed = True
        assert closed is True
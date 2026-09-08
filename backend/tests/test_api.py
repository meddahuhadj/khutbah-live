import main


def test_healthz(app_client):
    d = app_client.get("/healthz").json()
    assert d["ok"] is True
    assert "model" in d


def test_languages(app_client):
    langs = app_client.get("/api/languages").json()["languages"]
    codes = {l["code"] for l in langs}
    assert {"ar", "fr", "en", "nl"} <= codes


def test_create_session_returns_code_and_join_url(app_client):
    d = app_client.post("/api/session", json={"mosque_name": "Al-Furqan",
                                              "target_langs": ["fr", "en"]}).json()
    assert len(d["code"]) == 6
    assert d["broadcaster_token"]
    assert d["mosque_name"] == "Al-Furqan"
    assert d["target_langs"] == ["fr", "en"]
    assert d["join_url"].endswith("/?s=" + d["code"])


def test_create_session_rate_limited(app_client):
    codes = 0
    for _ in range(main._RL_MAX + 3):
        r = app_client.post("/api/session", json={})
        if r.status_code == 200:
            codes += 1
    assert codes == main._RL_MAX
    assert app_client.post("/api/session", json={}).status_code == 429


def test_get_session_404(app_client):
    assert app_client.get("/api/session/ZZZZZZ").status_code == 404


def test_get_session_state(app_client):
    code = app_client.post("/api/session", json={"mosque_name": "X"}).json()["code"]
    d = app_client.get(f"/api/session/{code}").json()
    assert d["code"] == code
    assert d["listeners"] == 0
    assert d["mosque_name"] == "X"


def test_qr_png(app_client):
    code = app_client.post("/api/session", json={}).json()["code"]
    r = app_client.get(f"/api/session/{code}/qr.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_lan_rewrite_for_localhost_host(app_client):
    # TestClient envoie Host: testserver -> pas 'localhost' -> pas de réécriture
    j = app_client.post("/api/session", json={}).json()
    assert "testserver" in j["join_url"]
    # Avec un Host localhost, base_url doit basculer sur l'IP LAN (ou rester localhost si introuvable)
    j2 = app_client.post("/api/session", json={}, headers={"host": "localhost:8000"}).json()
    assert j2["join_url"].startswith("http://")


def test_assets_path_traversal_blocked(app_client):
    assert app_client.get("/assets/..%2fmain.py").status_code == 404
    assert app_client.get("/assets/does-not-exist.jpg").status_code == 404


def test_index_and_manifest(app_client):
    assert app_client.get("/").status_code == 200
    m = app_client.get("/manifest.webmanifest").json()
    assert m["display"] == "standalone"

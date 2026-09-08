import main
from main import Room


def test_code_generation_unambiguous():
    code = main._gen_code()
    assert len(code) == 6
    assert not (set(code) & set("O0I1"))


def test_active_target_langs_from_listeners_and_defaults():
    r = Room("ABC123")
    r.default_langs = ["fr"]
    r.listeners = {"en": {object()}, "ar": {object()}, "nl": set()}
    langs = r.active_target_langs()
    assert "ar" not in langs           # l'original n'est jamais une cible
    assert set(langs) == {"fr", "en"}  # nl vide ignoré


def test_history_since_returns_only_missed():
    r = Room("ABC123")
    for i in range(1, 6):
        r.history.append({
            "seq": i, "ts": i, "arabic": f"a{i}", "translations": {"fr": f"t{i}"},
            "is_quran": False, "quran_ref": None,
        })
    missed = r.history_since("fr", 3)
    assert [p["seq"] for p in missed] == [4, 5]
    assert r.history_since("fr", 10) == []


def test_find_record():
    r = Room("ABC123")
    r.history.append({"seq": 7, "ts": 1, "arabic": "x", "translations": {},
                      "is_quran": False, "quran_ref": None})
    assert r.find_record(7)["arabic"] == "x"
    assert r.find_record(99) is None


def test_phrase_payload_projects_language():
    rec = {
        "seq": 1, "ts": 1, "arabic": "نص عربي",
        "translations": {"fr": "texte", "en": "text"},
        "is_quran": True, "quran_ref": "2:255", "is_hadith": False,
    }
    assert main._phrase_payload(rec, "fr")["text"] == "texte"
    assert main._phrase_payload(rec, "ar")["text"] == "نص عربي"
    assert main._phrase_payload(rec, "de")["text"] == ""   # langue absente
    assert main._phrase_payload(rec, "fr")["quran_ref"] == "2:255"


def test_fill_quran_ref_only_when_missing():
    rec = {"is_quran": True, "quran_ref": None, "arabic": "قُلْ هُوَ اللَّهُ أَحَدٌ"}
    main._fill_quran_ref(rec)
    assert rec["quran_ref"] == "112:1"
    assert rec["quran_ref_guessed"] is True

    kept = {"is_quran": True, "quran_ref": "S. 112", "arabic": "قل هو الله احد"}
    main._fill_quran_ref(kept)
    assert kept["quran_ref"] == "S. 112"
    assert "quran_ref_guessed" not in kept

    not_q = {"is_quran": False, "quran_ref": None, "arabic": "قل هو الله احد"}
    main._fill_quran_ref(not_q)
    assert not_q["quran_ref"] is None

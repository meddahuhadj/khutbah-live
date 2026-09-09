"""quran_verses.py -- le corpus canonique fige la traduction des versets."""
import quran_verses


def test_corpus_loads_and_contains_famous_verses():
    assert quran_verses.available()
    hit = quran_verses.canonical("2:255")
    assert hit is not None
    assert "fr" in hit["translations"]
    assert hit["ar"]


def test_canonical_returns_none_for_unknown_ref():
    assert quran_verses.canonical("9:999") is None
    assert quran_verses.canonical(None) is None
    assert quran_verses.canonical("") is None


def test_apply_overrides_only_known_languages():
    rec = {
        "is_quran": True,
        "quran_ref": "1:2",
        "arabic": "texte du modele",
        "translations": {"fr": "paraphrase du modele", "en": "model paraphrase"},
    }
    ok = quran_verses.apply(rec)
    assert ok is True
    assert rec["arabic"].startswith("ال")           # texte arabe fige
    assert rec["arabic"] != "texte du modele"
    assert rec["translations"]["fr"] != "paraphrase du modele"
    assert "en" not in rec["translations"] or rec["translations"]["en"] == "model paraphrase"
    assert "الأول" not in rec["arabic"]  # garde-fou trivial : arabe bien remplace


def test_apply_ignores_non_quran_or_without_ref():
    rec = {"is_quran": False, "quran_ref": "1:2",
           "translations": {"fr": "x"}}
    assert quran_verses.apply(rec) is False

    rec = {"is_quran": True, "quran_ref": None, "translations": {"fr": "x"}}
    assert quran_verses.apply(rec) is False


def test_apply_ignores_unknown_ref():
    rec = {"is_quran": True, "quran_ref": "9:999",
           "translations": {"fr": "x"}}
    assert quran_verses.apply(rec) is False
    assert rec["translations"] == {"fr": "x"}

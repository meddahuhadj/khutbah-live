import quran_index


def test_index_loads():
    assert quran_index.available()
    assert len(quran_index._refs) == 6236


def test_normalize_strips_diacritics_and_spaces():
    n = quran_index.normalize("قُلْ هُوَ اللَّهُ أَحَدٌ")
    assert n == "قلهواللهاحد"
    assert " " not in n


def test_normalize_unifies_alef_and_ta_marbuta():
    assert quran_index.normalize("إٱأآ") == "اااا"
    assert quran_index.normalize("رحمة") == "رحمه"


def test_find_short_full_verse():
    assert quran_index.find_ref("قُلْ هُوَ اللَّهُ أَحَدٌ") == "112:1"
    assert quran_index.find_ref("قُلْ أَعُوذُ بِرَبِّ النَّاسِ") == "114:1"


def test_find_basmala():
    assert quran_index.find_ref("بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ") == "1:1"


def test_find_partial_verse_quote():
    assert quran_index.find_ref(
        "وَاعْتَصِمُوا بِحَبْلِ اللَّهِ جَمِيعًا وَلَا تَفَرَّقُوا"
    ) == "3:103"
    assert quran_index.find_ref(
        "يَا أَيُّهَا الَّذِينَ آمَنُوا اتَّقُوا اللَّهَ وَقُولُوا قَوْلًا سَدِيدًا"
    ) == "33:70"


def test_non_quran_returns_none():
    assert quran_index.find_ref("إنما الأعمال بالنيات وإنما لكل امرئ ما نوى") is None
    assert quran_index.find_ref("السلام عليكم ورحمة الله وبركاته") is None


def test_too_short_returns_none():
    assert quran_index.find_ref("اتقوا الله") is None
    assert quran_index.find_ref("") is None

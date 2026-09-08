"""Reconstruit backend/data/quran_index.json depuis l'API alquran.cloud.

    python scripts/build_quran_index.py

Utilise EXACTEMENT la meme normalisation que quran_index.normalize() pour que
la recherche a l'execution corresponde a l'index.
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from quran_index import normalize  # noqa: E402

URL = "https://api.alquran.cloud/v1/quran/quran-simple"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "data", "quran_index.json")


def main() -> None:
    print("Telechargement du texte coranique...")
    raw = json.load(urllib.request.urlopen(URL, timeout=60))
    assert raw.get("status") == "OK", raw
    # L'edition "quran-simple" prefixe la basmala au 1er verset de chaque sourate
    # (sauf 1 et 9). On la retire pour ne pas fausser la recherche.
    basmala = normalize(raw["data"]["surahs"][0]["ayahs"][0]["text"])  # 1:1 = basmala
    refs, norm = [], []
    for surah in raw["data"]["surahs"]:
        s = surah["number"]
        for ay in surah["ayahs"]:
            n = normalize(ay["text"])
            if (ay["numberInSurah"] == 1 and s not in (1, 9)
                    and n.startswith(basmala) and len(n) > len(basmala)):
                n = n[len(basmala):]
            refs.append(f"{s}:{ay['numberInSurah']}")
            norm.append(n)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"refs": refs, "norm": norm}, f,
                  ensure_ascii=False, separators=(",", ":"))
    print(f"OK : {len(refs)} versets -> {OUT} ({os.path.getsize(OUT)//1024} Kio)")


if __name__ == "__main__":
    main()

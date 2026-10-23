"""
ordne_boege_alt_neu.py
----------------------
Das Böge-Testset (testfragen_boege_v2.csv) hat Gold-Chunk-IDs der ALTEN Wissensbasis (pypdf). Für die neue
(MinerU) Wissensbasis wird je Frage der Chunk gesucht, der den alten Gold-Chunk inhaltlich enthält.

Verfahren: Text beider Chunks normalisieren (Kleinbuchstaben, nur Buchstaben/Ziffern; Leerzeichen, Trennstriche,
Ligaturen und Sonderzeichen fallen weg) -> Zeichen-Fünfergruppen. Anteil der Fünfergruppen des alten Chunks, die
im neuen Chunk vorkommen (Containment). Gewählt wird der neue Chunk mit dem höchsten Anteil; bei Gleichstand
der mit der kleinsten Seitenabweichung. Neue Spalten: chunk_id (neu), zuordnung_anteil, chunk_id_alt.
Anteil < 0,6 = unsicher -> von Hand prüfen (die Textstelle kann in der neuen Extraktion anders aussehen
oder über zwei Chunks verteilt sein).

Start:
  python skripte/wissensbasis/ordne_boege_alt_neu.py daten/testfragen/testfragen_boege_v2.csv \
      daten/wissensbasen/knowledge_base_boege.json  daten/wissensbasen/knowledge_base_boege_v7b_ohne_register.json \
      daten/testfragen/testfragen_boege_v2_v7.csv
"""
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict


def norm(t):
    t = unicodedata.normalize("NFKD", t.lower())
    return re.sub(r"[^a-z0-9äöüß]", "", "".join(ch for ch in t if not unicodedata.combining(ch)))


def schindeln(t, n=5):
    t = norm(t)
    return {t[i:i + n] for i in range(max(0, len(t) - n + 1))}


def lade_chunks(pfad):
    with open(pfad, encoding="utf-8") as f:
        return json.load(f)["chunks"]


def main():
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    fragen_pfad, alt_pfad, neu_pfad, ausgabe = sys.argv[1:]
    alt = {c["id"]: c for c in lade_chunks(alt_pfad)}
    neu = lade_chunks(neu_pfad)
    neu_sch = [(c, schindeln(c["text"])) for c in neu]
    index = defaultdict(set)  # Fünfergruppe -> Positionen in neu_sch (Vorauswahl)
    for i, (_, s) in enumerate(neu_sch):
        for g in s:
            index[g].add(i)
    with open(fragen_pfad, encoding="utf-8", newline="") as f:
        zeilen = list(csv.DictReader(f))
    felder = list(zeilen[0].keys()) + [x for x in ("zuordnung_anteil", "chunk_id_alt") if x not in zeilen[0]]
    unsicher = 0
    for z in zeilen:
        a = alt.get(z["chunk_id"])
        z["chunk_id_alt"] = z["chunk_id"]
        if not a:
            z["zuordnung_anteil"] = "alt_fehlt"
            unsicher += 1
            continue
        s_alt = schindeln(a["text"])
        if not s_alt:
            z["zuordnung_anteil"] = "leer"; unsicher += 1; continue
        zaehler = defaultdict(int)
        for g in s_alt:
            for i in index.get(g, ()):
                zaehler[i] += 1
        if not zaehler:
            z["zuordnung_anteil"] = "0.00"; unsicher += 1; continue
        seite_alt = a.get("seite") or 0
        beste = max(zaehler, key=lambda i: (zaehler[i], -abs((neu_sch[i][0].get("seite") or 0) - seite_alt)))
        anteil = zaehler[beste] / len(s_alt)
        z["chunk_id"] = neu_sch[beste][0]["id"]
        z["zuordnung_anteil"] = f"{anteil:.2f}"
        if anteil < 0.6:
            unsicher += 1
        print(f"nr {z.get('nr')}: {z['chunk_id_alt']} -> {z['chunk_id']}  Anteil {anteil:.2f}  Seite alt {seite_alt} neu {neu_sch[beste][0].get('seite')}")
    with open(ausgabe, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=felder)
        w.writeheader()
        w.writerows(zeilen)
    print(f"\n{len(zeilen)} Fragen, davon unsicher (< 0,6 oder fehlend): {unsicher}  ->  {ausgabe}")


if __name__ == "__main__":
    main()

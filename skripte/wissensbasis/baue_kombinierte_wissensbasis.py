"""
baue_kombinierte_wissensbasis.py
--------------------------------
Fügt zwei Wissensbasen (z. B. Fischer + Böge) zu einer Datei zusammen, damit Fragen aus beiden
Büchern gestellt werden können. Texte bleiben unverändert; jeder Chunk bekommt zusätzlich das
Feld "buch". Bei doppelten Chunk-IDs (beide Bücher zählen pdf_0001, pdf_0002, ...) bekommen die
IDs des ERSTEN Buchs ein Präfix (fischer_pdf_0001); die IDs des zweiten Buchs bleiben gleich.

Start (im Projektordner):
  python skripte/wissensbasis/baue_kombinierte_wissensbasis.py \
      daten/wissensbasen/knowledge_base_fischer_v7c.json Fischer \
      daten/wissensbasen/knowledge_base_boege.json Böge \
      daten/wissensbasen/knowledge_base_fischer_boege.json
"""
import json
import sys
from collections import Counter


def lade(pfad, buch):
    with open(pfad, "r", encoding="utf-8") as f:
        daten = json.load(f)
    chunks = daten["chunks"]
    for c in chunks:
        c["buch"] = buch
    return daten, chunks


def main():
    if len(sys.argv) != 6:
        sys.exit(__doc__)
    pfad_a, name_a, pfad_b, name_b, ausgabe = sys.argv[1:]
    daten_a, chunks_a = lade(pfad_a, name_a)
    _, chunks_b = lade(pfad_b, name_b)
    doppelt = [i for i, n in Counter(c["id"] for c in chunks_a + chunks_b).items() if n > 1]
    if doppelt:
        # Beide Bücher zählen ihre Chunks pdf_0001, pdf_0002, ... -> die IDs des ERSTEN Buchs bekommen
        # ein Präfix (fischer_pdf_0001). Die IDs des zweiten Buchs bleiben unverändert, damit dessen
        # Testfragen-CSV weiter gilt. Fischer-Testfragen danach neu zuordnen (ordne_chunks_zu.py).
        praefix = name_a.lower() + "_"
        for c in chunks_a:
            c["id"] = praefix + c["id"]
        print(f"{len(doppelt)} doppelte IDs -> IDs von {name_a} mit Präfix '{praefix}' versehen")
        rest = [i for i, n in Counter(c["id"] for c in chunks_a + chunks_b).items() if n > 1]
        if rest:
            sys.exit(f"ABBRUCH: auch nach dem Präfix {len(rest)} doppelte IDs, z. B. {rest[:5]}")
    ergebnis = {k: v for k, v in daten_a.items() if k != "chunks"}
    ergebnis["quellen"] = [pfad_a, pfad_b]
    ergebnis["chunks"] = chunks_a + chunks_b
    with open(ausgabe, "w", encoding="utf-8") as f:
        json.dump(ergebnis, f, ensure_ascii=False)
    print(f"{ausgabe}: {len(chunks_a)} ({name_a}) + {len(chunks_b)} ({name_b}) = {len(ergebnis['chunks'])} Chunks")


if __name__ == "__main__":
    main()

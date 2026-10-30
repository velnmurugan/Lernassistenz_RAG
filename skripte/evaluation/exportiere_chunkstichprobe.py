"""
exportiere_chunkstichprobe.py
-----------------------------
Zieht eine zufällige, nach Kapitel geschichtete Stichprobe von Chunks aus einer Wissensbasis,
damit daraus neue, ungetunte Testfragen geschrieben werden können (die Wissensbasis ist
nicht einsehbar, nur diese Stichprobe).

- feste Zufallszahl (--seed), damit die Stichprobe reproduzierbar ist
- schließt Chunks aus, die schon als Gold in einer vorhandenen Testfragen-CSV stehen
  (Spalte chunk_id) sowie deren direkte Nachbarn (1-Satz-Überlappung)
- nimmt nur Textchunks mittlerer Länge (--min-woerter/--max-woerter), keine Bild-/Formelchunks
- Ausgabe: <ausgabe>.txt (zum Hochladen) und <ausgabe>.json (Chunk-IDs, Seiten)

Start (im Ordner ~/RAG):
  python skripte/evaluation/exportiere_chunkstichprobe.py \
      --kb daten/wissensbasen/knowledge_base_boege.json \
      --ausschluss daten/testfragen/testfragen_v1.csv \
      --n 45 --seed 2026 --ausgabe evaluationsdaten/boege_stichprobe
"""
import argparse
import csv
import json
import random
import re
from collections import defaultdict
from pathlib import Path


def kapitel(thema):
    m = re.match(r"\s*(\d+)", thema or "")
    return m.group(1) if m else "?"


def buchstabenanteil(t):
    return sum(c.isalpha() for c in t) / max(1, len(t))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--ausschluss", nargs="*", default=[], help="Testfragen-CSVs mit Spalte chunk_id")
    ap.add_argument("--n", type=int, default=45)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--min-woerter", type=int, default=40)
    ap.add_argument("--max-woerter", type=int, default=400)
    ap.add_argument("--ausgabe", default="evaluationsdaten/chunkstichprobe")
    a = ap.parse_args()

    chunks = json.load(open(a.kb, encoding="utf-8"))["chunks"]
    ids = [c["id"] for c in chunks]
    pos = {cid: i for i, cid in enumerate(ids)}

    gesperrt = set()
    for pfad in a.ausschluss:
        with open(pfad, encoding="utf-8", newline="") as f:
            for z in csv.DictReader(f):
                cid = (z.get("chunk_id") or "").strip()
                if cid in pos:
                    i = pos[cid]
                    gesperrt.update(ids[max(0, i - 1): i + 2])
    print(f"{len(gesperrt)} Chunks (Gold + Nachbarn) ausgeschlossen")

    ws = sorted(len(c["text"].split()) for c in chunks)
    print(f"Chunklänge in Wörtern: Median {ws[len(ws)//2]}, 10%-Quantil {ws[len(ws)//10]}, 90%-Quantil {ws[9*len(ws)//10]}")
    kand = defaultdict(list)
    for c in chunks:
        w = len(c["text"].split())
        if c["id"] in gesperrt or c.get("typ", "text") != "text" or c.get("bild"):
            continue
        if not (a.min_woerter <= w <= a.max_woerter) or buchstabenanteil(c["text"]) < 0.75:
            continue
        kand[kapitel(c.get("thema", ""))].append(c)
    gesamt = sum(len(v) for v in kand.values())
    print(f"{gesamt} geeignete Kandidaten in {len(kand)} Kapiteln")

    rnd = random.Random(a.seed)
    wahl = []
    # proportional zur Kapitelgröße, mindestens 1 je Kapitel
    for k in sorted(kand, key=lambda x: (len(x), x)):
        q = max(1, round(a.n * len(kand[k]) / gesamt))
        wahl += rnd.sample(kand[k], min(q, len(kand[k])))
    rnd.shuffle(wahl)
    wahl = wahl[: a.n] if len(wahl) > a.n else wahl
    wahl.sort(key=lambda c: pos[c["id"]])

    ziel = Path(a.ausgabe)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    with open(ziel.with_suffix(".txt"), "w", encoding="utf-8") as f:
        for c in wahl:
            f.write(f"=== {c['id']} | S. {c.get('seite', '?')} | {c.get('thema', '')} ===\n{c['text']}\n\n")
    json.dump([{"id": c["id"], "seite": c.get("seite"), "thema": c.get("thema")} for c in wahl],
              open(ziel.with_suffix(".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(wahl)} Chunks -> {ziel.with_suffix('.txt')}  (diese Datei hochladen)")
    print("Kapitelverteilung:", {k: sum(kapitel(c.get('thema', '')) == k for c in wahl) for k in sorted(kand)})


if __name__ == "__main__":
    main()

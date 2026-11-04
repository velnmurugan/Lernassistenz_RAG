"""
rang300.py  (Fragen300, Schritt 2: Rang der Buchstelle in der Trefferliste, für Recall@k und MRR)
Dieselbe Suche wie die App (rp.retrieval, hybrid_kg_rr; das Sprachmodell erhält die ersten 4). Ein Abschnitt zählt als Treffer,
wenn mindestens 40 % seiner Wortfolgen (4 Wörter) auf der Buchseite der Frage stehen (Seitentext aus dem PDF, daten/gold300.json;
bei zwei Seiten beide). Rang = Platz des ersten Treffers unter den ersten 50, 0 = nicht unter den ersten 50.
Kein Sprachmodell nötig. Fortsetzbar.
  python skripte/evaluation/rang300.py F300-V20 --gold daten/testfragen/gold300.json
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401

import argparse
import csv
import json
import re
import unicodedata
from pathlib import Path

import rag_pipeline as rp

TIEFE = 50
SCHWELLE = 0.4
FELDER = ["id", "buch", "rang", "bester_anteil_top50", "top4_ids", "top4_wie_antwort"]


def woerter(t):
    t = unicodedata.normalize("NFKC", t or "").lower()
    t = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", t)
    return re.findall(r"[0-9a-zäöüß]+", t)


def schindeln(w, n=4):
    return {tuple(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--gold", default="daten/testfragen/gold300.json")
    ap.add_argument("--fragen", default="daten/testfragen/fragen300.csv")
    ap.add_argument("--kb", default="daten/wissensbasen/knowledge_base_fischer_boege_v7r.json")
    ap.add_argument("--retrieval", default="hybrid_kg_rr")
    a = ap.parse_args()
    gold = json.load(open(a.gold, encoding="utf-8"))
    fragen = [q for q in csv.DictReader(open(a.fragen, encoding="utf-8")) if q["id"] in gold]
    antworten = {}
    p_ant = Path("evaluationsdaten") / f"antworten300_{a.label}.csv"
    if p_ant.exists():
        antworten = {z["id"]: z.get("quellen_mit", "") for z in csv.DictReader(open(p_ant, encoding="utf-8"))}
    out = Path("evaluationsdaten") / f"rang300_{a.label}.csv"
    alt = {z["id"]: z for z in csv.DictReader(open(out, encoding="utf-8"))} if out.exists() else {}
    chunks = rp.lade_wissensbasis(a.kb)
    zeilen = []
    for q in fragen:
        if q["id"] in alt:
            zeilen.append(alt[q["id"]])
            continue
        ziel = schindeln(woerter(gold[q["id"]]["text"]))
        top, alle = rp.retrieval(q["frage"], chunks, top_k=4, methode=a.retrieval)
        rang, bester = 0, 0.0
        for i, c in enumerate(alle[:TIEFE], 1):
            s = schindeln(woerter(c.get("text", "")))
            anteil = len(s & ziel) / len(s) if len(s) >= 5 else 0.0
            bester = max(bester, anteil)
            if anteil >= SCHWELLE and not rang:
                rang = i
        ids = "; ".join(c["id"] for c in top)
        z = {"id": q["id"], "buch": q["buch"], "rang": rang, "bester_anteil_top50": round(bester, 2), "top4_ids": ids,
             "top4_wie_antwort": "" if q["id"] not in antworten else ("ja" if antworten[q["id"]] == ids else "nein")}
        zeilen.append(z)
        print(f"[{q['id']:>4}] Rang {rang:>2}  (bester Anteil {bester:.2f})", flush=True)
        with open(out, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FELDER)
            w.writeheader()
            w.writerows(zeilen + [alt[i] for i in alt if i not in {x["id"] for x in zeilen}])
    r = [int(z["rang"]) for z in zeilen]
    n = len(r)
    print(f"Fertig: {out}  n={n}  Recall@1={sum(x == 1 for x in r) / n:.3f}  Recall@4={sum(1 <= x <= 4 for x in r) / n:.3f}  "
          f"MRR={sum(1 / x for x in r if x) / n:.3f}  nicht unter 50: {sum(x == 0 for x in r)}")


if __name__ == "__main__":
    main()

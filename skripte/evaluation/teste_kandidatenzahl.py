"""
teste_kandidatenzahl.py
-----------------------
Retrieval-only test (no LLM): how many first-stage candidates does the cross-encoder
need? Runs hybrid_kg_rr with reranker.RERANK_KANDIDATEN = 50 / 35 / 25 (default) on
development questions and reports Recall@4, Recall@4 + neighbour, MRR, median rank of
the gold chunk and retrieval time. Also lists every question whose result changes.

Use development sets only (NOT N100): the candidate count is a tuning decision.

Start (project folder, env pilot_rag active):
  python skripte/evaluation/teste_kandidatenzahl.py \
      --kb daten/wissensbasen/knowledge_base_fischer_boege.json \
      --fragen daten/testfragen/testfragen_fischer_v1_chunks_beide.csv daten/testfragen/testfragen_v1.csv \
      --namen Fischer Boege --kandidaten 50 35 25
Output: console + evaluationsdaten/kandidatenzahl_<Zeitstempel>.csv (one row per question and count).
"""
import sys as _sys, pathlib as _pl  # Projektpfade (lernassistent/pfadsetup.py)
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import argparse
import csv
import datetime
import statistics
import time
from pathlib import Path

import rag_pipeline
import reranker


def nachbar_ids(chunk_id):
    """fischer_pdf_0012 -> {fischer_pdf_0011, fischer_pdf_0013}; pdf_3734 -> {pdf_3733, pdf_3735}."""
    stamm, nr_text = chunk_id.rsplit("_", 1)
    nr, breite = int(nr_text), len(nr_text)
    return {f"{stamm}_{nr - 1:0{breite}d}", f"{stamm}_{nr + 1:0{breite}d}"}


def metriken(zeilen):
    """zeilen: list of dicts with 'rang' (int or None), 'treffer', 'treffer_nb', 'sek'."""
    n = len(zeilen)
    raenge = [z["rang"] for z in zeilen if z["rang"]]
    return {
        "n": n,
        "R@4": sum(z["treffer"] for z in zeilen),
        "R@4+Nb": sum(z["treffer_nb"] for z in zeilen),
        "MRR": sum(1 / z["rang"] for z in zeilen if z["rang"]) / n if n else 0.0,
        "Median Rang": statistics.median(raenge) if raenge else None,
        "in Kandidaten": None,  # filled by caller (depends on count)
        "Median s": statistics.median(z["sek"] for z in zeilen) if zeilen else 0.0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--fragen", nargs="+", required=True, help="one or more question CSVs with chunk_id")
    ap.add_argument("--namen", nargs="+", default=None, help="labels for the question sets")
    ap.add_argument("--kandidaten", nargs="+", type=int, default=[50, 35, 25])
    ap.add_argument("--rrf-k", type=int, default=5)
    ap.add_argument("--methode", default="hybrid_kg_rr")
    args = ap.parse_args()
    namen = args.namen or [Path(f).stem for f in args.fragen]
    assert len(namen) == len(args.fragen), "--namen must match --fragen"
    rag_pipeline.RRF_K = args.rrf_k

    chunks = rag_pipeline.lade_wissensbasis(args.kb)
    ids = {c["id"] for c in chunks}
    print(f"{len(chunks)} Chunks, Methode {args.methode}, RRF_K={rag_pipeline.RRF_K}, Kandidaten {args.kandidaten}")
    rag_pipeline.retrieval("Aufwärmen", chunks, top_k=4, methode=args.methode)  # warm-up (models, graph, BM25)

    alle_zeilen = []  # for CSV
    for name, pfad in zip(namen, args.fragen):
        with open(pfad, encoding="utf-8") as f:
            fragen = [q for q in csv.DictReader(f) if (q.get("chunk_id") or "").strip()]
        fehlend = [q["nr"] for q in fragen if q["chunk_id"].strip() not in ids]
        if fehlend:
            print(f"[{name}] WARNUNG: gold chunk not in this KB for questions {fehlend} (skipped)")
            fragen = [q for q in fragen if q["chunk_id"].strip() in ids]
        print(f"\n=== {name}: {len(fragen)} questions with gold chunk ({pfad})")
        ergebnis = {n: [] for n in args.kandidaten}
        for q in fragen:
            gold = q["chunk_id"].strip()
            for n in args.kandidaten:
                reranker.RERANK_KANDIDATEN = n
                t0 = time.time()
                top, alle = rag_pipeline.retrieval(q["frage"], chunks, top_k=4, methode=args.methode)
                sek = time.time() - t0
                rang = next((i + 1 for i, c in enumerate(alle) if c["id"] == gold), None)
                top_ids = {c["id"] for c in top}
                z = {"satz": name, "nr": q["nr"], "kandidaten": n, "gold": gold, "rang": rang,
                     "treffer": gold in top_ids,
                     "treffer_nb": gold in top_ids or bool(nachbar_ids(gold) & top_ids),
                     "sek": round(sek, 1)}
                ergebnis[n].append(z)
                alle_zeilen.append(z)
            print(f"  nr {q['nr']:>3}: " + "  ".join(
                f"{n}: Rang {ergebnis[n][-1]['rang']}" for n in args.kandidaten), flush=True)

        print(f"\n{name}: results by candidate count")
        print(f"{'Kand.':>6} {'n':>3} {'R@4':>5} {'R@4+Nb':>7} {'MRR':>6} {'MedRang':>8} {'inKand':>7} {'Med s':>6}")
        for n in args.kandidaten:
            m = metriken(ergebnis[n])
            in_k = sum(1 for z in ergebnis[n] if z["rang"] and z["rang"] <= n)
            # reranked candidates come first in the list, so rank <= n means: gold was among the candidates
            print(f"{n:>6} {m['n']:>3} {m['R@4']:>5} {m['R@4+Nb']:>7} {m['MRR']:>6.3f} "
                  f"{str(m['Median Rang']):>8} {in_k:>7} {m['Median s']:>6.1f}")

        basis = args.kandidaten[0]
        for n in args.kandidaten[1:]:
            geaendert = [(a, b) for a, b in zip(ergebnis[basis], ergebnis[n])
                         if a["treffer"] != b["treffer"] or a["treffer_nb"] != b["treffer_nb"]]
            print(f"\n{name}: questions where {n} candidates differ from {basis} in top-4 hit:")
            if not geaendert:
                print("  none")
            for a, b in geaendert:
                print(f"  nr {a['nr']}: rank {a['rang']} -> {b['rang']}  "
                      f"(hit {a['treffer']} -> {b['treffer']}, with neighbour {a['treffer_nb']} -> {b['treffer_nb']})")

    ziel = Path("evaluationsdaten") / f"kandidatenzahl_{datetime.datetime.now():%Y%m%d_%H%M}.csv"
    ziel.parent.mkdir(exist_ok=True)
    with open(ziel, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["satz", "nr", "kandidaten", "gold", "rang", "treffer", "treffer_nb", "sek"])
        w.writeheader()
        w.writerows(alle_zeilen)
    print(f"\nSaved: {ziel}")


if __name__ == "__main__":
    main()

"""
frage_testen.py
---------------
Eine einzelne Frage durch die Pipeline schicken und ALLES anzeigen:
Start-Begriffe des Graphen, die Top-k-Chunks mit ihrem Rang in jeder
Einzelliste (dense / bm25 / graph), den vollen Chunk-Text und die
dreistufige Antwort von qwen.

Schreibt NICHTS in evaluationsdaten/interaktionen.csv (verfälscht keine Läufe).

Start:
  python frage_testen.py "Was bringt der D-Anteil in einem Regler?"
  python frage_testen.py "Was bringt der D-Anteil in einem Regler?" --retrieval hybrid,hybrid_kg
  python frage_testen.py "…" --retrieval hybrid_kg --rrf-k 5 --nur-retrieval
"""
import argparse
import textwrap

import rag_pipeline
from rag_pipeline import lade_wissensbasis, retrieval, beantworte_frage

KB_PFAD = "knowledge_base.json"
BREITE = 100


def raenge(frage, chunks, methode):
    _, alle = retrieval(frage, chunks, top_k=1, methode=methode)
    return {c["id"]: i for i, c in enumerate(alle, start=1)}


def block(titel, text):
    print(f"\n  {titel}")
    for zeile in textwrap.wrap(text or "—", BREITE):
        print(f"    {zeile}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frage")
    ap.add_argument("--retrieval", default="hybrid_kg", help="eine oder mehrere, kommagetrennt")
    ap.add_argument("--rrf-k", type=int, default=5)
    ap.add_argument("--top-k", type=int, default=4)
    ap.add_argument("--nur-retrieval", action="store_true", help="ohne LLM-Antwort")
    args = ap.parse_args()
    rag_pipeline.RRF_K = args.rrf_k
    chunks = lade_wissensbasis(KB_PFAD)
    frage = args.frage

    rang = {m: raenge(frage, chunks, m) for m in ("dense", "bm25")}
    methoden = [m.strip() for m in args.retrieval.split(",") if m.strip()]
    if any(m in ("graph", "hybrid_kg") for m in methoden):
        import numpy as np
        import wissensgraph
        scores, d = wissensgraph.graph_scores(frage, chunks, details=True)
        g = d["graph"]
        reihenfolge = np.argsort(-scores, kind="stable")
        rang["graph"] = {g["chunk_ids"][ci]: (i + 1 if scores[ci] > 0 else None)
                         for i, ci in enumerate(reihenfolge)}
        print("Start-Begriffe Graph:", ", ".join(
            f"{g['labels'][i]} ({h})" for i, (_, h) in sorted(d["seeds"].items(), key=lambda t: -t[1][0]))
            or "— keine")

    for m in methoden:
        print("\n" + "=" * BREITE)
        print(f"Frage: {frage}\nRetrieval: {m}  (RRF_K={rag_pipeline.RRF_K}, top_k={args.top_k})")
        print("=" * BREITE)
        if args.nur_retrieval:
            top, _ = retrieval(frage, chunks, top_k=args.top_k, methode=m)
            ergebnis = None
        else:
            ergebnis = beantworte_frage(frage, chunks, top_k=args.top_k, methode=m)
            top = ergebnis["top_chunks"]

        for nr, c in enumerate(top, start=1):
            r = "  ".join(f"{q}={rang[q].get(c['id']) or '–'}" for q in ("dense", "bm25", "graph") if q in rang)
            print(f"\n[{nr}] {c['id']}  Seite {c.get('seite', '?')}  | {c.get('thema', '')[:50]}")
            print(f"    Rang in Einzellisten: {r}   Kosinus={c['score']:.3f}")
            for zeile in textwrap.wrap(c["text"], BREITE):
                print(f"    │ {zeile}")

        if ergebnis is not None:
            print("\n" + "-" * BREITE)
            if not ergebnis["genuegend_relevanz"]:
                print(f"VERWEIGERT (Schwelle): bester Kosinus {ergebnis['bester_score']:.3f} "
                      f"< {rag_pipeline.RELEVANZ_SCHWELLE}")
            block("STUFE 1 – Hinweis:", ergebnis.get("hinweis"))
            block("STUFE 2 – Erklärung:", ergebnis.get("erklaerung"))
            block("STUFE 3 – Lösung:", ergebnis.get("loesung"))
            if not ergebnis.get("vollstaendig_geparst"):
                print("\n  (Hinweis: Antwort nicht im 3-Stufen-Format geparst)")


if __name__ == "__main__":
    main()
"""
retrieval_vergleich.py
----------------------
Schnellvergleich der Retrieval-Methoden aus rag_pipeline.retrieval()
(dense / bm25 / hybrid) — nur Retrieval, ohne LLM, in ~1 Minute.
Optionaler Vorab-Check; die eigentliche Bewertung erfolgt über
fuehre_testfragen_aus.py + ragas_auswertung.py.

Nutzt exakt dieselbe retrieval()-Funktion wie die Pipeline, damit der
Vergleich das tatsächliche Verhalten widerspiegelt.

Metriken (nur Fragen mit bekanntem Quell-Chunk in testfragen_v1.csv):
  Recall@k     Anteil Fragen, deren Quell-Chunk unter den Top-k liegt (k = 4, 10, 50)
  R@4 +Nachb.  wie Recall@4, aber auch der direkt benachbarte Chunk zählt
  MRR          Mittelwert von 1/Rang des Quell-Chunks
  Median-Rang  robust gegen einzelne Extremwerte
Werte sind eine UNTERGRENZE: Steht dieselbe Information zusätzlich in einem
anderen Chunk, zählt ein Treffer dort nicht.

Varianten-Syntax: dense | bm25 | hybrid | hybrid@K  (K = RRF-Konstante, Standard
RRF_K aus rag_pipeline). Kleines K gewichtet Spitzenplätze stärker: ein Chunk
auf Platz 2 in EINER Liste schlägt dann einen Chunk auf Platz 10 in beiden.
Zusätzlich: "Vereinigung@k" = Anteil Fragen, deren Quell-Chunk in den Top-k
von dense ODER bm25 liegt — Obergrenze dafür, was ein Reranker über diese
Kandidaten (geplante V3) erreichen könnte.

Start:
  python retrieval_vergleich.py
  python retrieval_vergleich.py --varianten dense,bm25,hybrid@5
Ergebnis: evaluationsdaten/retrieval_vergleich.csv
"""
import argparse
import csv
import statistics
import time
from pathlib import Path

import rag_pipeline
from rag_pipeline import lade_wissensbasis, retrieval, LOG_VERZEICHNIS

KB_PFAD = "knowledge_base.json"
TESTFRAGEN = Path("testfragen_v1.csv")
ERGEBNIS = LOG_VERZEICHNIS / "retrieval_vergleich.csv"
K_WERTE = (4, 10, 50)


def nachbar_ids(chunk_id):
    nr = int(chunk_id.split("_")[-1])
    return {f"pdf_{nr - 1:04d}", f"pdf_{nr + 1:04d}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--varianten", default="dense,bm25,hybrid@60,hybrid@20,hybrid@10,hybrid@5,hybrid@2")
    args = ap.parse_args()
    varianten = [v.strip() for v in args.varianten.split(",") if v.strip()]

    chunks = lade_wissensbasis(KB_PFAD)
    ids = {c["id"] for c in chunks}
    with open(TESTFRAGEN, encoding="utf-8") as f:
        fragen = [q for q in csv.DictReader(f) if q["chunk_id"].strip() in ids]
    print(f"{len(chunks)} Chunks, {len(fragen)} Fragen mit Quell-Chunk, Varianten={varianten}")
    print("(erster Aufruf: Embeddings + BM25-Index werden aufgebaut)\n")

    zeilen = []
    t0 = time.time()
    for q in fragen:
        erwartet = q["chunk_id"].strip()
        nachbarn = nachbar_ids(erwartet)
        zeile = {"nr": q["nr"], "typ": q["typ"], "frage": q["frage"], "erwarteter_chunk": erwartet}
        for v in varianten:
            methode, _, k = v.partition("@")
            rrf_alt = rag_pipeline.RRF_K
            if k:
                rag_pipeline.RRF_K = int(k)
            try:
                top, alle = retrieval(q["frage"], chunks, top_k=4, methode=methode)
            finally:
                rag_pipeline.RRF_K = rrf_alt
            rang = {c["id"]: i for i, c in enumerate(alle, start=1)}
            zeile[f"rang_{v}"] = rang[erwartet]
            zeile[f"rang_nachbar_{v}"] = min([rang[erwartet]] + [rang[n] for n in nachbarn if n in rang])
            zeile[f"top4_{v}"] = "; ".join(c["id"] for c in top)
        zeilen.append(zeile)
    print(f"Laufzeit {time.time() - t0:.0f}s\n")

    n = len(zeilen)
    kopf = f"{'Variante':<11}" + "".join(f"{'R@' + str(k):>8}" for k in K_WERTE) + f"{'R@4+Nb':>9}{'MRR':>8}{'Median':>9}"
    print(kopf)
    print("-" * len(kopf))
    for v in varianten:
        r = [z[f"rang_{v}"] for z in zeilen]
        rn = [z[f"rang_nachbar_{v}"] for z in zeilen]
        rec = "".join(f"{sum(x <= k for x in r):>5}/{n:<2}" for k in K_WERTE)
        print(f"{v:<11}{rec}{sum(x <= 4 for x in rn):>6}/{n:<2}"
              f"{statistics.mean(1 / x for x in r):>8.3f}{statistics.median(r):>9.0f}")

    if "dense" in varianten and "bm25" in varianten:
        for k in (10, 20, 50):
            u = sum(z["rang_dense"] <= k or z["rang_bm25"] <= k for z in zeilen)
            print(f"{'Vereinigung@' + str(k):<11}{u:>5}/{n:<2}  (Quell-Chunk in Top-{k} von dense ODER bm25)")

    print("\nRang des Quell-Chunks pro Frage (✓ = in Top-4):")
    print(f"{'Nr':>3} {'Typ':<12}" + "".join(f"{v:>11}" for v in varianten) + "  Frage")
    for z in zeilen:
        werte = "".join(f"{z[f'rang_{v}']:>10}{'✓' if z[f'rang_{v}'] <= 4 else ' '}" for v in varianten)
        print(f"{z['nr']:>3} {z['typ']:<12}{werte}  {z['frage'][:55]}")

    felder = ["nr", "typ", "frage", "erwarteter_chunk"]
    for v in varianten:
        felder += [f"rang_{v}", f"rang_nachbar_{v}", f"top4_{v}"]
    with open(ERGEBNIS, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=felder)
        w.writeheader()
        w.writerows(zeilen)
    print(f"\nDetails: {ERGEBNIS}")


if __name__ == "__main__":
    main()
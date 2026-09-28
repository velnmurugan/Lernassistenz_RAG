"""
fuehre_testfragen_aus.py
------------------------
Schickt alle Fragen aus testfragen_v1.csv durch die echte Pipeline
(beantworte_frage), protokolliert sie wie die Studien-App in
evaluationsdaten/interaktionen.csv und schreibt einen Retrieval-Bericht
(evaluationsdaten/testlauf_retrieval.csv).

Setzt einen abgebrochenen Lauf automatisch fort: Fragen, die für dieselbe
Sitzungs-ID schon im Log stehen, werden übersprungen.

Start: python fuehre_testfragen_aus.py [SITZUNGS_ID]   (Standard: TEST-01)
"""
import csv
import sys
import time
from pathlib import Path

import requests

from rag_pipeline import (
    lade_wissensbasis, berechne_kb_hash, beantworte_frage, retrieval,
    protokolliere_interaktion, INTERAKTIONS_LOG, LOG_VERZEICHNIS,
)

TESTFRAGEN = Path("testfragen_v1.csv")
KB_PFAD = "knowledge_base.json"
BERICHT = LOG_VERZEICHNIS / "testlauf_retrieval.csv"
SITZUNGS_ID = sys.argv[1] if len(sys.argv) > 1 else "TEST-01"
TOP_K = 4
FELDER = ["nr", "typ", "frage", "erwarteter_chunk", "top_ids", "bester_score",
          "genuegend_relevanz", "vollstaendig_geparst", "sekunden",
          "rang_erwartet", "treffer_exakt", "treffer_inkl_nachbar", "fehler"]


def nachbar_ids(chunk_id):
    """pdf_3734 -> {pdf_3733, pdf_3735} (1-Satz-Überlappung, siehe _gruppen_zu_chunks)."""
    nr = int(chunk_id.split("_")[-1])
    return {f"pdf_{nr - 1:04d}", f"pdf_{nr + 1:04d}"}


def ist_wahr(x):
    """Werte aus einem wieder eingelesenen CSV sind Strings ('True'/'False')."""
    return x if isinstance(x, bool) else str(x) == "True"


def mit_wiederholung(frage, chunks, versuche=3, wartezeit=20):
    """Fängt kurze Ollama-Ausfälle ab (z. B. Neustart nach Absturz)."""
    for v in range(1, versuche + 1):
        try:
            return beantworte_frage(frage, chunks, top_k=TOP_K)
        except requests.exceptions.ConnectionError:
            if v == versuche:
                raise
            print(f"     Ollama nicht erreichbar, neuer Versuch in {wartezeit}s ({v}/{versuche})")
            time.sleep(wartezeit)


def main():
    # Fortsetzung: bereits geloggte Fragen dieser Sitzung überspringen
    bereits = set()
    if INTERAKTIONS_LOG.exists():
        with open(INTERAKTIONS_LOG, encoding="utf-8") as f:
            bereits = {r["frage"] for r in csv.DictReader(f) if r.get("sitzungs_id") == SITZUNGS_ID}

    bericht = []
    if bereits and BERICHT.exists():
        with open(BERICHT, encoding="utf-8") as f:
            bericht = [z for z in csv.DictReader(f) if not z.get("fehler") and z["frage"] in bereits]
        print(f"Fortsetzung: {len(bereits)} Fragen von '{SITZUNGS_ID}' bereits im Log — werden übersprungen.")

    with open(TESTFRAGEN, encoding="utf-8") as f:
        fragen = [q for q in csv.DictReader(f) if q["frage"] not in bereits]

    if not fragen:
        print("Alle Fragen bereits verarbeitet.")
    else:
        chunks = lade_wissensbasis(KB_PFAD)
        kb_hash = berechne_kb_hash(KB_PFAD)
        print(f"{len(fragen)} offene Fragen, {len(chunks)} Chunks, kb_hash={kb_hash}, Sitzung={SITZUNGS_ID}\n")

    for q in fragen:
        t0 = time.time()
        try:
            ergebnis = mit_wiederholung(q["frage"], chunks)
        except Exception as e:
            print(f"[{q['nr']:>2}] FEHLER: {e}")
            bericht.append({"nr": q["nr"], "typ": q["typ"], "frage": q["frage"], "fehler": str(e)})
            continue
        dauer = time.time() - t0

        ergebnis["kb_hash"] = kb_hash
        # Stufe 3: im Batchlauf gilt die volle Antwort als 'gesehen'. Uptake-Werte
        # aus TEST-Sitzungen werden nicht als Nutzungsverhalten interpretiert.
        protokolliere_interaktion(SITZUNGS_ID, ergebnis, scaffolding_stufe_erreicht=3)

        top_ids = [c["id"] for c in ergebnis["top_chunks"]]
        erwartet = q["chunk_id"].strip()
        zeile = {
            "nr": q["nr"], "typ": q["typ"], "frage": q["frage"],
            "erwarteter_chunk": erwartet, "top_ids": "; ".join(top_ids),
            "bester_score": round(ergebnis["bester_score"], 4),
            "genuegend_relevanz": ergebnis["genuegend_relevanz"],
            "vollstaendig_geparst": ergebnis["vollstaendig_geparst"],
            "sekunden": round(dauer, 1),
        }
        if erwartet:
            _, alle = retrieval(q["frage"], chunks, top_k=TOP_K)
            zeile["rang_erwartet"] = next((i + 1 for i, c in enumerate(alle) if c["id"] == erwartet), "")
            zeile["treffer_exakt"] = erwartet in top_ids
            zeile["treffer_inkl_nachbar"] = erwartet in top_ids or bool(nachbar_ids(erwartet) & set(top_ids))
        bericht.append(zeile)

        status = "VERWEIGERT" if not ergebnis["genuegend_relevanz"] else f"Rang {zeile.get('rang_erwartet', '-')}"
        print(f"[{q['nr']:>2}] {q['typ']:<12} score={zeile['bester_score']:.3f}  {status:<12} {dauer:5.1f}s")

    bericht.sort(key=lambda z: int(z["nr"]))
    with open(BERICHT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FELDER, extrasaction="ignore", restval="")
        w.writeheader()
        w.writerows(bericht)

    ok = [z for z in bericht if not z.get("fehler")]
    mit_chunk = [z for z in ok if z.get("erwarteter_chunk")]
    aussen = [z for z in ok if z["typ"] == "ausserhalb"]
    generiert = [z for z in ok if ist_wahr(z["genuegend_relevanz"])]
    print(f"\n--- Zusammenfassung ({len(ok)}/{len(bericht)} Fragen ohne Fehler) ---")
    if mit_chunk:
        print(f"Recall@{TOP_K} exakt:           {sum(ist_wahr(z['treffer_exakt']) for z in mit_chunk)}/{len(mit_chunk)}")
        print(f"Recall@{TOP_K} inkl. Nachbar:   {sum(ist_wahr(z['treffer_inkl_nachbar']) for z in mit_chunk)}/{len(mit_chunk)}")
    if aussen:
        print(f"Korrekt verweigert (außerhalb): {sum(not ist_wahr(z['genuegend_relevanz']) for z in aussen)}/{len(aussen)}")
    if generiert:
        print(f"3-Stufen-Format eingehalten:    {sum(ist_wahr(z['vollstaendig_geparst']) for z in generiert)}/{len(generiert)}")
    print(f"Bericht: {BERICHT}")


if __name__ == "__main__":
    main()
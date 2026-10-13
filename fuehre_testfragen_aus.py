"""
fuehre_testfragen_aus.py
------------------------
Schickt alle Fragen aus testfragen_v1.csv durch die echte Pipeline
(beantworte_frage), protokolliert sie wie die Studien-App in
evaluationsdaten/interaktionen.csv und schreibt einen Retrieval-Bericht
(evaluationsdaten/testlauf_retrieval_<SITZUNGS_ID>.csv).

Die Sitzungs-ID dient als Versionskennung (z. B. V1-HYBRID) und wird später
in ragas_auswertung.py als Filter verwendet.

Setzt einen abgebrochenen Lauf automatisch fort: Fragen, die für dieselbe
Sitzungs-ID schon im Log stehen, werden übersprungen.

Start:
  python fuehre_testfragen_aus.py V0-DENSE  --retrieval dense
  python fuehre_testfragen_aus.py V1-HYBRID --retrieval hybrid --rrf-k 2
  python fuehre_testfragen_aus.py V1-BM25   --retrieval bm25
  python fuehre_testfragen_aus.py V2-KG     --retrieval hybrid_kg --rrf-k 5
  python fuehre_testfragen_aus.py V3-RR     --retrieval hybrid_kg_rr --rrf-k 5 --scaffolding S3-v0
  python fuehre_testfragen_aus.py V4-S2     --retrieval hybrid_kg_rr --rrf-k 5   # 2 Stufen (S2-v1)
  python fuehre_testfragen_aus.py TEST-01                     # Standard (RETRIEVAL_METHODE)
"""
import argparse
import csv
import datetime
import json
import subprocess
import time
from pathlib import Path

import requests

import rag_pipeline
from rag_pipeline import (
    lade_wissensbasis, berechne_kb_hash, beantworte_frage, retrieval,
    protokolliere_interaktion, INTERAKTIONS_LOG, LOG_VERZEICHNIS,
)

TESTFRAGEN = Path("testfragen_v1.csv")
KB_PFAD = "knowledge_base.json"
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


def mit_wiederholung(frage, chunks, methode, versuche=3, wartezeit=20):
    """Fängt kurze Ollama-Ausfälle ab (z. B. Neustart nach Absturz)."""
    for v in range(1, versuche + 1):
        try:
            return beantworte_frage(frage, chunks, top_k=TOP_K, methode=methode)
        except requests.exceptions.ConnectionError:
            if v == versuche:
                raise
            print(f"     Ollama nicht erreichbar, neuer Versuch in {wartezeit}s ({v}/{versuche})")
            time.sleep(wartezeit)


def schreibe_lauf_konfiguration(sitzungs_id, methode, kb_hash, n_chunks):
    """Speichert alle Einstellungen dieses Laufs in evaluationsdaten/lauf_<ID>.json,
    damit jedes Ergebnis seiner exakten Konfiguration zugeordnet werden kann
    (Reproduzierbarkeit, Methodenteil)."""
    def befehl(*args):
        try:
            return subprocess.run(args, capture_output=True, text=True, timeout=5).stdout.strip()
        except Exception:
            return ""
    try:
        ollama_version = requests.get(rag_pipeline.OLLAMA_URL.replace("/api/generate", "/api/version"),
                                      timeout=3).json().get("version", "")
    except Exception:
        ollama_version = ""
    konfig = {
        "sitzungs_id": sitzungs_id,
        "zeitstempel": datetime.datetime.now().isoformat(timespec="seconds"),
        "git_commit": befehl("git", "rev-parse", "--short", "HEAD"),
        "git_uncommitted_changes": bool(befehl("git", "status", "--porcelain", "--untracked-files=no")),
        "kb_hash": kb_hash,
        "anzahl_chunks": n_chunks,
        "retrieval_methode": methode,
        "rrf_k": rag_pipeline.RRF_K,
        "top_k": TOP_K,
        "relevanz_schwelle": rag_pipeline.RELEVANZ_SCHWELLE,
        "generator_modell": rag_pipeline.MODEL_NAME,
        "generierungs_optionen": rag_pipeline.GENERIERUNGS_OPTIONEN,
        "scaffolding_version": rag_pipeline.SCAFFOLDING_VERSION,
        "embedding_modell": rag_pipeline.EMBEDDING_MODELL_NAME,
        "ollama_version": ollama_version,
        "testfragen_datei": str(TESTFRAGEN),
    }
    if methode.endswith("_rr"):
        import reranker
        konfig["reranker"] = reranker.parameter()
    if methode.replace("_rr", "") in ("graph", "hybrid_kg"):
        import wissensgraph
        konfig["kg_gewicht"] = rag_pipeline.KG_GEWICHT
        konfig["kg_parameter"] = wissensgraph.parameter()
    pfad = LOG_VERZEICHNIS / f"lauf_{sitzungs_id}.json"
    if not pfad.exists():  # bei Fortsetzung eines Laufs die ursprüngliche Konfiguration behalten
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(konfig, f, ensure_ascii=False, indent=2)
    if konfig["git_uncommitted_changes"]:
        print("HINWEIS: Code hat nicht committete Änderungen — für saubere Läufe vorher committen.")
    return pfad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sitzungs_id", nargs="?", default="TEST-01", help="Versionskennung, z. B. V1-HYBRID")
    ap.add_argument("--retrieval", choices=["dense", "bm25", "hybrid", "graph", "hybrid_kg", "hybrid_rr", "hybrid_kg_rr"], default=None,
                    help=f"Retrieval-Methode (Standard: {rag_pipeline.RETRIEVAL_METHODE})")
    ap.add_argument("--rrf-k", type=int, default=None,
                    help=f"RRF-Konstante für hybrid (Standard: {rag_pipeline.RRF_K})")
    ap.add_argument("--scaffolding", choices=sorted(rag_pipeline.SCAFFOLDING_MARKER_VERSIONEN), default=None,
                    help=f"Stufen-Prompt (Standard: {rag_pipeline.SCAFFOLDING_VERSION}; S3-v0 = V0–V3)")
    args = ap.parse_args()
    sitzungs_id = args.sitzungs_id
    methode = args.retrieval or rag_pipeline.RETRIEVAL_METHODE
    if args.rrf_k is not None:
        rag_pipeline.RRF_K = args.rrf_k
    if args.scaffolding:
        rag_pipeline.SCAFFOLDING_VERSION = args.scaffolding
    bericht_datei = LOG_VERZEICHNIS / f"testlauf_retrieval_{sitzungs_id}.csv"

    # Fortsetzung: bereits geloggte Fragen dieser Sitzung überspringen
    bereits = set()
    if INTERAKTIONS_LOG.exists():
        with open(INTERAKTIONS_LOG, encoding="utf-8") as f:
            bereits = {r["frage"] for r in csv.DictReader(f) if r.get("sitzungs_id") == sitzungs_id}

    bericht = []
    if bereits and bericht_datei.exists():
        with open(bericht_datei, encoding="utf-8") as f:
            bericht = [z for z in csv.DictReader(f) if not z.get("fehler") and z["frage"] in bereits]
        print(f"Fortsetzung: {len(bereits)} Fragen von '{sitzungs_id}' bereits im Log — werden übersprungen.")

    with open(TESTFRAGEN, encoding="utf-8") as f:
        fragen = [q for q in csv.DictReader(f) if q["frage"] not in bereits]

    if not fragen:
        print("Alle Fragen bereits verarbeitet.")
    else:
        chunks = lade_wissensbasis(KB_PFAD)
        kb_hash = berechne_kb_hash(KB_PFAD)
        konfig_pfad = schreibe_lauf_konfiguration(sitzungs_id, methode, kb_hash, len(chunks))
        print(f"Konfiguration: {konfig_pfad}")
        print(f"{len(fragen)} offene Fragen, {len(chunks)} Chunks, kb_hash={kb_hash}, "
              f"Sitzung={sitzungs_id}, Retrieval={methode}, RRF_K={rag_pipeline.RRF_K}, "
              f"Generierung={rag_pipeline.GENERIERUNGS_OPTIONEN}, Stufen={rag_pipeline.SCAFFOLDING_VERSION}\n")

    for q in fragen:
        t0 = time.time()
        try:
            ergebnis = mit_wiederholung(q["frage"], chunks, methode)
        except Exception as e:
            print(f"[{q['nr']:>2}] FEHLER: {e}")
            bericht.append({"nr": q["nr"], "typ": q["typ"], "frage": q["frage"], "fehler": str(e)})
            continue
        dauer = time.time() - t0

        ergebnis["kb_hash"] = kb_hash
        # Letzte Stufe (3 bei S3-v0, 2 bei S2-v1): im Batchlauf gilt die volle Antwort als 'gesehen'. Uptake-Werte
        # aus Testsitzungen werden nicht als Nutzungsverhalten interpretiert.
        protokolliere_interaktion(sitzungs_id, ergebnis,
                                  scaffolding_stufe_erreicht=len(rag_pipeline.scaffolding_marker()))

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
            _, alle = retrieval(q["frage"], chunks, top_k=TOP_K, methode=methode)
            zeile["rang_erwartet"] = next((i + 1 for i, c in enumerate(alle) if c["id"] == erwartet), "")
            zeile["treffer_exakt"] = erwartet in top_ids
            zeile["treffer_inkl_nachbar"] = erwartet in top_ids or bool(nachbar_ids(erwartet) & set(top_ids))
        bericht.append(zeile)

        status = "VERWEIGERT" if not ergebnis["genuegend_relevanz"] else f"Rang {zeile.get('rang_erwartet', '-')}"
        print(f"[{q['nr']:>2}] {q['typ']:<12} score={zeile['bester_score']:.3f}  {status:<12} {dauer:5.1f}s")

    bericht.sort(key=lambda z: int(z["nr"]))
    with open(bericht_datei, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FELDER, extrasaction="ignore", restval="")
        w.writeheader()
        w.writerows(bericht)

    ok = [z for z in bericht if not z.get("fehler")]
    mit_chunk = [z for z in ok if z.get("erwarteter_chunk")]
    aussen = [z for z in ok if z["typ"] == "ausserhalb"]
    generiert = [z for z in ok if ist_wahr(z["genuegend_relevanz"])]
    print(f"\n--- Zusammenfassung {sitzungs_id} / {methode} ({len(ok)}/{len(bericht)} Fragen ohne Fehler) ---")
    if mit_chunk:
        print(f"Recall@{TOP_K} exakt:           {sum(ist_wahr(z['treffer_exakt']) for z in mit_chunk)}/{len(mit_chunk)}")
        print(f"Recall@{TOP_K} inkl. Nachbar:   {sum(ist_wahr(z['treffer_inkl_nachbar']) for z in mit_chunk)}/{len(mit_chunk)}")
    if aussen:
        print(f"Korrekt verweigert (außerhalb): {sum(not ist_wahr(z['genuegend_relevanz']) for z in aussen)}/{len(aussen)}")
    if generiert:
        print(f"Stufen-Format eingehalten:      {sum(ist_wahr(z['vollstaendig_geparst']) for z in generiert)}/{len(generiert)}")
    print(f"Bericht: {bericht_datei}")


if __name__ == "__main__":
    main()

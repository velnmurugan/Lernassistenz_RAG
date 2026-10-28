"""V16: N100 nur mit RAG (ohne Vergleichslauf ohne RAG). Liest die beiden N100-Dateien, schickt jede Frage durch die Pipeline wie die
App (top_k 4, hybrid_kg_rr, KB v7r) und schreibt je Frage eine Zeile (alle Spalten der Testfrage + Antwort + Prüfung). Ergebnis nach
jeder Frage gespeichert. Spaltennamen werden erkannt (id/nr, frage).
Start (aus ~/RAG, gewünschte Version exportiert):  python skripte/evaluation/lauf_n100_rag.py V16"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import csv, os, time
import rag_pipeline as rp

KB = "daten/wissensbasen/knowledge_base_fischer_boege_v7r.json"
DATEIEN = [("F", "daten/testfragen/testfragen_fischer_v2.csv"), ("B", "daten/testfragen/testfragen_boege_v2.csv")]
AUS_FELDER = ["n100_id", "status", "rechen_pruefung", "sekunden", "loesung", "hinweis", "rechen_befund", "quellen", "loesung_original",
              "loesung_denk", "rb_roh", "fehler"]


def spalte(zeile, namen):
    for n in namen:
        for k in zeile:
            if k.strip().lower() == n:
                return k
    return None


def main():
    label = _sys.argv[1]
    chunks = rp.lade_wissensbasis(KB)
    aus = f"evaluationsdaten/n100_rag_{label}.csv"
    fertig = set()
    if os.path.exists(aus):
        fertig = {r["n100_id"] for r in csv.DictReader(open(aus, encoding="utf-8"))}
    print(f"Version: RP={rp.RECHEN_PRUEFUNG_VERSION}{'+v12' if getattr(rp, 'RP_V12', False) else ''} RB={getattr(rp, 'NACHRECHNUNG_VERSION', '') or '-'} "
          f"G={rp.SCAFFOLDING_VERSION} FS={os.environ.get('LERNASSISTENT_FS', 'FS-v2')} CTX={rp.KONTEXT_TOKENS} -> {aus}", flush=True)
    zeilen = []
    for praefix, datei in DATEIEN:
        if not os.path.exists(datei):
            print(f"FEHLT: {datei}", flush=True)
            continue
        for z in csv.DictReader(open(datei, encoding="utf-8")):
            zeilen.append((praefix, z))
    felder = AUS_FELDER + sorted({k for _, z in zeilen for k in z if k not in AUS_FELDER})
    neu = not os.path.exists(aus)
    with open(aus, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=felder, extrasaction="ignore")
        if neu:
            w.writeheader()
        for praefix, z in zeilen:
            kid, kfr = spalte(z, ("id", "nr", "frage_id", "fid")), spalte(z, ("frage", "question"))
            roh_id = (z.get(kid) or "").strip() if kid else str(len(fertig) + 1)
            n100_id = roh_id if roh_id[:1].upper() in ("F", "B") else f"{praefix}{roh_id}"
            if n100_id in fertig or not kfr:
                continue
            t0 = time.perf_counter()
            out = dict(z, n100_id=n100_id)
            try:
                e = rp.beantworte_frage(z[kfr], chunks, top_k=4, methode="hybrid_kg_rr")
                out.update({k: e.get(k, "") for k in ("status", "rechen_pruefung", "loesung", "hinweis", "rechen_befund",
                                                      "loesung_original", "loesung_denk", "rb_roh")})
                out["quellen"] = "; ".join(q["id"] for q in e.get("quellen", []))
            except Exception as ex:
                out["fehler"] = f"{type(ex).__name__}: {ex}"[:300]
            out["sekunden"] = round(time.perf_counter() - t0, 1)
            w.writerow(out); fh.flush()
            print(f"{n100_id:5} {out.get('status', ''):18} {out.get('rechen_pruefung', ''):22} {out['sekunden']:6.0f} s | "
                  f"{(out.get('loesung') or out.get('fehler', ''))[:90]!r}", flush=True)
    print(f"Datei: {aus}", flush=True)


if __name__ == "__main__":
    main()

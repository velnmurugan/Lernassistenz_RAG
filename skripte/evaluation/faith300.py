"""
faith300.py  (Fragen300, Schritt 4: Faithfulness mit und ohne RAG)
Wie faithfulness_rag_vs_ohne.py (29 Oct 2026): beide Antworten einer Buchfrage werden gegen DIESELBEN vier Abschnitte geprüft,
die das System für die Frage abgerufen hat (quellen_mit). Funktionen aus ragas_auswertung.py (Prompts J-v1: Antwort in
Aussagen zerlegen, jede Aussage gegen den Kontext prüfen), Richter wie in richter300.py (Standard gemma4:12b).
Faithfulness = gestützte Aussagen / prüfbare Aussagen. Nur Buchfragen. Fortsetzbar.
  python skripte/evaluation/faith300.py F300-V20 --richter gemma4:12b [--limit 4]
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))

import argparse
import csv
import json
import time
from pathlib import Path

import rag_pipeline as rp
import ragas_auswertung as ra

FELDER = ["id", "buch", "typ", "seite", "faithfulness", "aussagen", "gestuetzt", "unlesbar", "meta_verworfen", "sek", "richter"]


def lies(p):
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--richter", default="gemma4:12b")
    ap.add_argument("--kb", default="daten/wissensbasen/knowledge_base_fischer_boege_v7r.json")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    ra.PROMPT_VERSION = "J-v1"
    lookup = {c["id"]: c for c in rp.lade_wissensbasis(a.kb)}
    ant = [z for z in lies(Path("evaluationsdaten") / f"antworten300_{a.label}.csv") if z["buch"] != "Außerhalb"][: a.limit]
    out = Path("evaluationsdaten") / f"faith300_{a.label}.csv"
    det = Path("evaluationsdaten") / f"faith300_{a.label}_details.jsonl"
    fertig = {(z["id"], z["seite"]): z for z in lies(out)} if out.exists() else {}
    zeilen = list(fertig.values())
    for z in ant:
        ids = [i.strip() for i in (z.get("quellen_mit") or "").split(";") if i.strip()]
        kontext = rp._material_text([lookup[i] for i in ids if i in lookup])
        if not kontext:
            continue
        for seite in ("ohne", "mit"):
            if (z["id"], seite) in fertig:
                continue
            antwort = z.get(f"antwort_{seite}", "")
            if not antwort or antwort.startswith("FEHLER"):
                continue
            t0 = time.time()
            aussagen, verworfen = ra.extrahiere_statements(z["frage"], antwort, a.richter)
            details = []
            for s in aussagen:
                u, b = ra.pruefe_statement_gestuetzt(s, kontext, a.richter)
                details.append({"aussage": s, "urteil": u, "begruendung": b})
            gueltig = [d for d in details if d["urteil"] is not None]
            score = round(sum(d["urteil"] for d in gueltig) / len(gueltig), 4) if gueltig else ""
            neu = {"id": z["id"], "buch": z["buch"], "typ": z["typ"], "seite": seite, "faithfulness": score,
                   "aussagen": len(details), "gestuetzt": sum(1 for d in gueltig if d["urteil"]),
                   "unlesbar": len(details) - len(gueltig), "meta_verworfen": verworfen,
                   "sek": round(time.time() - t0, 1), "richter": a.richter}
            zeilen.append(neu)
            with open(det, "a", encoding="utf-8") as f:
                f.write(json.dumps({"id": z["id"], "seite": seite, "details": details}, ensure_ascii=False) + "\n")
            with open(out, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=FELDER)
                w.writeheader()
                w.writerows(zeilen)
            print(f"[{z['id']:>4}] {seite:<4} F={score!s:<6} ({neu['gestuetzt']}/{len(gueltig)} Aussagen) {neu['sek']} s", flush=True)
    for s in ("ohne", "mit"):
        v = [float(x["faithfulness"]) for x in zeilen if x["seite"] == s and x["faithfulness"] != ""]
        print(f"Faithfulness {s}: n={len(v)} Mittel={sum(v) / len(v):.3f}" if v else f"Faithfulness {s}: keine Werte")


if __name__ == "__main__":
    main()

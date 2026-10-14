"""
teste_ideen.py
--------------
Feste Prüfung von Hinweis und "Deine Idee?"-Rückmeldung mit vorbereiteten Lernenden-Ideen
(daten/testfragen/testideen_fischer_v1.csv: 36 Ideen zu 11 Fragen; Typen: richtig, Einheit/Vorzeichen
fehlt, falsch konkret, vage, Meta-Frage, außerhalb des Buchs, gefährlich).

Je Frage wird EINMAL beantwortet (Hinweis + Lösung, inkl. Hinweis-Prüfung), dann jede Idee einzeln
bewertet (gib_feedback, inkl. Rückmeldungs-Prüfung). Ausgabe: evaluationsdaten/ideen_test_<SITZUNG>.csv
mit automatischen Prüfungen und leeren Spalten für die Handbewertung:
  bewertung_korrekt    ja / nein          (sachlich richtig, kein Widerspruch zur Lösung)
  bewertung_verraet    nein / teilweise / ja
  bewertung_hilfreich  1 (nicht) / 2 (etwas) / 3 (klar hilfreich)
  anmerkung

Start (Ollama läuft, Umgebung pilot_rag):
  python skripte/evaluation/teste_ideen.py V8D-IDEEN \
      --kb daten/wissensbasen/knowledge_base_fischer_v7b.json --retrieval hybrid_kg_rr
Dauer grob 15–30 min.
"""
import sys as _sys, pathlib as _pl  # Projektpfade (lernassistent/pfadsetup.py)
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import argparse
import collections
import csv
import time
from pathlib import Path

import rag_pipeline as rp
import ideen_feedback as fbm

FELDER = ["id", "frage_id", "ideen_typ", "idee", "urteil_erwartet", "urteil", "urteil_passt",
          "status", "hinweis", "hinweis_pruefung", "hinweis_original",
          "rueckmeldung", "feedback_pruefung", "rueckmeldung_original",
          "leck_zahlen", "neue_zahlen", "verweis_material", "sekunden",
          "loesung", "frage", "versionen",
          "bewertung_korrekt", "bewertung_verraet", "bewertung_hilfreich", "anmerkung"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sitzung")
    ap.add_argument("--kb", default="daten/wissensbasen/knowledge_base_fischer_v7b.json")
    ap.add_argument("--ideen", default="daten/testfragen/testideen_fischer_v1.csv")
    ap.add_argument("--retrieval", default="hybrid_kg_rr")
    args = ap.parse_args()

    chunks = rp.lade_wissensbasis(args.kb)
    kb_hash = rp.berechne_kb_hash(args.kb)
    with open(args.ideen, encoding="utf-8") as f:
        ideen = list(csv.DictReader(f))
    versionen = (f"{rp.SCAFFOLDING_VERSION}/{rp.HINWEIS_PRUEFUNG_VERSION}/"
                 f"{fbm.FEEDBACK_PROMPT_VERSION}/{fbm.FEEDBACK_PRUEFUNG_VERSION}")
    print(f"{len(ideen)} Ideen, KB {args.kb} ({kb_hash}), Retrieval {args.retrieval}, Versionen {versionen}")

    antworten, zeilen = {}, []
    for z in ideen:
        q = z["frage"]
        if q not in antworten:
            t0 = time.time()
            erg = rp.beantworte_frage(q, chunks, methode=args.retrieval)
            erg["kb_hash"] = kb_hash
            antworten[q] = erg
            print(f"\n[{z['frage_id']}] {erg.get('status')} | Hinweis ({erg.get('hinweis_pruefung')}): "
                  f"{erg.get('hinweis', '')[:90]}  ({time.time() - t0:.0f} s)")
        erg = antworten[q]
        if not fbm.idee_moeglich(erg):
            fb = {"urteil": "-", "rueckmeldung": "(kein Ideen-Feld: Status " + str(erg.get("status")) + ")",
                  "sekunden": 0}
        else:
            fb = fbm.gib_feedback(erg, z["idee"])
        passt = "ja" if fb["urteil"] == z["urteil_erwartet"] else "nein"
        print(f"  {z['id']} {z['ideen_typ']:<22} erwartet {z['urteil_erwartet']:<10} -> {fb['urteil']:<10} "
              f"FP={fb.get('feedback_pruefung', '')}")
        zeilen.append({
            "id": z["id"], "frage_id": z["frage_id"], "ideen_typ": z["ideen_typ"], "idee": z["idee"],
            "urteil_erwartet": z["urteil_erwartet"], "urteil": fb["urteil"], "urteil_passt": passt,
            "status": erg.get("status", ""), "hinweis": erg.get("hinweis", ""),
            "hinweis_pruefung": erg.get("hinweis_pruefung", ""), "hinweis_original": erg.get("hinweis_original", ""),
            "rueckmeldung": fb["rueckmeldung"], "feedback_pruefung": fb.get("feedback_pruefung", ""),
            "rueckmeldung_original": fb.get("rueckmeldung_original", ""),
            "leck_zahlen": "; ".join(fb.get("leck_zahlen", [])), "neue_zahlen": "; ".join(fb.get("neue_zahlen", [])),
            "verweis_material": "; ".join(fb.get("verweis_material", [])), "sekunden": fb.get("sekunden", 0),
            "loesung": erg.get("loesung", ""), "frage": q, "versionen": versionen,
        })

    ziel = rp.LOG_VERZEICHNIS / f"ideen_test_{args.sitzung}.csv"
    with open(ziel, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FELDER, restval="")
        w.writeheader()
        w.writerows(zeilen)

    print("\n=== Zusammenfassung (automatisch) ===")
    print(f"Urteil wie erwartet:        {sum(z['urteil_passt'] == 'ja' for z in zeilen)}/{len(zeilen)}")
    print(f"Hinweis-Prüfung je Frage:   {dict(collections.Counter(a.get('hinweis_pruefung', '') for a in antworten.values()))}")
    print(f"Rückmeldungs-Prüfung:       {dict(collections.Counter(z['feedback_pruefung'] for z in zeilen))}")
    print(f"Gezeigt mit Lösungszahl:    {sum(bool(z['leck_zahlen']) for z in zeilen)}")
    print(f"Gezeigt mit neuer Zahl:     {sum(bool(z['neue_zahlen']) for z in zeilen)}")
    nach_typ = collections.defaultdict(list)
    for z in zeilen:
        nach_typ[z["urteil_erwartet"]].append(z["urteil_passt"] == "ja")
    print("Urteil passt je erwartetem Urteil:", {k: f"{sum(v)}/{len(v)}" for k, v in nach_typ.items()})
    print(f"\nDatei für die Handbewertung: {ziel}")


if __name__ == "__main__":
    main()

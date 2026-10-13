"""
teste_ideen_feedback.py
-----------------------
Prüft die "Deine Idee?"-Rückmeldung (ideen_feedback.py) mit vorbereiteten
Lernenden-Ideen (testideen_v1.csv: 8 Fragen x 4 Ideentypen richtig / teilweise /
falsch / keine_idee). Die Ideen und das erwartete Urteil hat Claude entworfen ->
vor der Auswertung von Vel prüfen (Limitation wie beim Testfragensatz).

Pro Frage wird die Antwort einmal mit der echten Pipeline erzeugt (wie in der
Studien-App, aber mit wählbarem Retrieval), danach bekommt jede Idee eine
Rückmeldung. Nichts davon geht in interaktionen.csv oder ideen_feedback.csv.

Automatisch gemessen:
  - Urteil-Treffer: stimmt das Urteil des Modells mit dem erwarteten überein?
  - Format: wurde RUECKMELDUNG geparst?
  - Leck-Verdacht: Zahlen aus der Lösung in der Rückmeldung (nur Zahlen!)
Leere Spalten für die menschliche Bewertung (Scaffolding-Spezifikation §7,
Skala ja / teilweise / nein): S1 verrät Lösung, S2 hilfreich, Fehler erkannt.

Start (Ollama muss laufen):
  python teste_ideen_feedback.py IF-v1 --retrieval hybrid_kg_rr --rrf-k 5
Ergebnis: evaluationsdaten/test_ideen_feedback_<LABEL>.csv
"""
import argparse
import csv
import time
from collections import Counter, defaultdict
from pathlib import Path

import rag_pipeline
from rag_pipeline import lade_wissensbasis, berechne_kb_hash, beantworte_frage, LOG_VERZEICHNIS
from ideen_feedback import gib_feedback, idee_moeglich, FEEDBACK_PROMPT_VERSION

TESTFRAGEN = Path("testfragen_v1.csv")
TESTIDEEN = Path("testideen_v1.csv")
KB_PFAD = "knowledge_base.json"
FELDER = ["nr", "frage", "ideentyp", "idee", "urteil_erwartet", "urteil", "urteil_treffer",
          "rueckmeldung", "ueberlegung", "geparst", "leck_zahlen", "sekunden",
          "hinweis", "loesung", "prompt_version", "retrieval",
          "S1_verraet_loesung", "S2_hilfreich", "fehler_erkannt", "kommentar"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label", nargs="?", default=FEEDBACK_PROMPT_VERSION)
    ap.add_argument("--retrieval", default="hybrid_kg_rr")
    ap.add_argument("--rrf-k", type=int, default=5)
    args = ap.parse_args()
    rag_pipeline.RRF_K = args.rrf_k

    with open(TESTFRAGEN, encoding="utf-8") as f:
        fragen = {r["nr"]: r["frage"] for r in csv.DictReader(f)}
    with open(TESTIDEEN, encoding="utf-8") as f:
        ideen = list(csv.DictReader(f))
    pro_frage = defaultdict(list)
    for i in ideen:
        pro_frage[i["nr"]].append(i)

    chunks = lade_wissensbasis(KB_PFAD)
    kb_hash = berechne_kb_hash(KB_PFAD)
    print(f"{len(ideen)} Ideen zu {len(pro_frage)} Fragen, Retrieval={args.retrieval}, "
          f"RRF_K={rag_pipeline.RRF_K}, Prompt={FEEDBACK_PROMPT_VERSION}, kb_hash={kb_hash}\n")

    zeilen = []
    for nr, liste in pro_frage.items():
        t0 = time.time()
        ergebnis = beantworte_frage(fragen[nr], chunks, top_k=4, methode=args.retrieval)
        print(f"[Q{nr}] Antwort in {time.time() - t0:.0f}s: {fragen[nr][:60]}")
        if not idee_moeglich(ergebnis):
            print("      kein Ideen-Feld (Gate, Parse-Fehler oder Verweigerung) -> übersprungen")
            continue
        for i in liste:
            try:
                fb = gib_feedback(ergebnis, i["idee"])
            except Exception as e:
                print(f"      {i['ideentyp']:<11} FEHLER: {e}")
                continue
            treffer = fb["urteil"] == i["urteil_erwartet"]
            print(f"      {i['ideentyp']:<11} -> {fb['urteil']:<10} {'ok ' if treffer else 'ABW'} "
                  f"{'LECK? ' + ','.join(fb['leck_zahlen']) if fb['leck_zahlen'] else ''}")
            zeilen.append({
                "nr": nr, "frage": fragen[nr], "ideentyp": i["ideentyp"], "idee": i["idee"],
                "urteil_erwartet": i["urteil_erwartet"], "urteil": fb["urteil"], "urteil_treffer": treffer,
                "rueckmeldung": fb["rueckmeldung"], "ueberlegung": fb["ueberlegung"],
                "geparst": fb["geparst"], "leck_zahlen": "; ".join(fb["leck_zahlen"]),
                "sekunden": fb["sekunden"], "hinweis": ergebnis["hinweis"], "loesung": ergebnis["loesung"],
                "prompt_version": FEEDBACK_PROMPT_VERSION, "retrieval": args.retrieval,
            })

    pfad = LOG_VERZEICHNIS / f"test_ideen_feedback_{args.label}.csv"
    with open(pfad, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FELDER, restval="")
        w.writeheader()
        w.writerows(zeilen)

    if zeilen:
        n = len(zeilen)
        print(f"\n--- Zusammenfassung {args.label} ({n} Rückmeldungen) ---")
        print(f"Format geparst:      {sum(z['geparst'] for z in zeilen)}/{n}")
        print(f"Urteil wie erwartet: {sum(z['urteil_treffer'] for z in zeilen)}/{n}")
        for typ in ("richtig", "teilweise", "falsch", "keine_idee"):
            t = [z for z in zeilen if z["ideentyp"] == typ]
            if t:
                print(f"   {typ:<11} {sum(z['urteil_treffer'] for z in t)}/{len(t)}   "
                      f"Urteile: {dict(Counter(z['urteil'] for z in t))}")
        print(f"Leck-Verdacht (Zahlen): {sum(bool(z['leck_zahlen']) for z in zeilen)}/{n}")
        print(f"Median Sekunden:     {sorted(z['sekunden'] for z in zeilen)[n // 2]}")
    print(f"Ergebnis: {pfad}  (Spalten S1/S2/fehler_erkannt von Hand ausfüllen)")


if __name__ == "__main__":
    main()

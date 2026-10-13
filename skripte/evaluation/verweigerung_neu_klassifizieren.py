"""
verweigerung_neu_klassifizieren.py
----------------------------------
Wendet den verbesserten Verweigerungs-Detektor (ragas_auswertung.ist_modell_verweigerung,
VERWEIGERUNGS_DETEKTOR = "v2") nachträglich auf alle archivierten Versionen an —
OHNE die Richter-Aufrufe zu wiederholen.

Warum das genügt: Die Verweigerungs-Erkennung entscheidet nur, ob ein Fall als
Antwort bewertet wird (Faithfulness, Answer Relevance) oder als Verweigerung zählt.
Context Relevance wird für beide berechnet und bleibt unverändert. Fälle, die jetzt
als Verweigerung erkannt werden, verlieren ihre (sinnlosen) Antwort-Metriken.

Pro Versionsordner in evaluationsdaten/archiv/:
  - Sicherung ragas_ergebnisse_detektor_v1.csv (nur beim ersten Lauf)
  - ragas_ergebnisse.csv mit korrigierter Klassifikation + Spalte verweigerungs_detektor

Start:
  python verweigerung_neu_klassifizieren.py            # nur anzeigen (Trockenlauf)
  python verweigerung_neu_klassifizieren.py --schreiben
"""
import sys as _sys, pathlib as _pl  # Projektpfade (lernassistent/pfadsetup.py)
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import argparse
import csv
import shutil
from pathlib import Path

from ragas_auswertung import ist_modell_verweigerung, VERWEIGERUNGS_DETEKTOR
from rag_pipeline import INTERAKTIONS_LOG, LOG_VERZEICHNIS

ARCHIV = LOG_VERZEICHNIS / "archiv"
ANTWORT_METRIKEN = ["n_aussagen", "n_gestuetzt", "n_unlesbar", "n_meta_verworfen",
                    "faithfulness", "answer_relevance", "ar_roh", "ausweichend"]


def lade_loesungen():
    loesung = {}
    with open(INTERAKTIONS_LOG, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            loesung[(r["sitzungs_id"], r["frage"])] = r["loesung"]  # letzter Eintrag gewinnt
    return loesung


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schreiben", action="store_true")
    args = ap.parse_args()
    loesungen = lade_loesungen()

    for ordner in sorted(p for p in ARCHIV.iterdir() if p.is_dir()):
        datei = ordner / "ragas_ergebnisse.csv"
        if not datei.exists():
            continue
        with open(datei, encoding="utf-8") as f:
            leser = csv.DictReader(f)
            felder = list(leser.fieldnames)
            zeilen = list(leser)
        if "verweigerungs_detektor" not in felder:
            felder.append("verweigerungs_detektor")

        geaendert, fehlend = [], 0
        for z in zeilen:
            text = loesungen.get((z["sitzungs_id"], z["frage"]))
            if text is None:
                fehlend += 1
            elif z["modell_verweigerung"] != "True" and ist_modell_verweigerung(text):
                geaendert.append((z["fall_id"], z.get("faithfulness", ""), z.get("ausweichend", ""), text[:90]))
                z["modell_verweigerung"] = "True"
                for m in ANTWORT_METRIKEN:
                    if m in z:
                        z[m] = ""
            z["verweigerungs_detektor"] = VERWEIGERUNGS_DETEKTOR

        print(f"\n{ordner.name}: {len(geaendert)} Fall/Fälle neu als Verweigerung erkannt"
              + (f"  (⚠ {fehlend} ohne Antworttext im Log)" if fehlend else ""))
        for fid, faith, ausw, anfang in geaendert:
            print(f"   {fid}  vorher faith={faith or '–'} ausweichend={ausw or '–'}  | {anfang}…")

        if args.schreiben:
            sicherung = ordner / "ragas_ergebnisse_detektor_v1.csv"
            if not sicherung.exists():
                shutil.copy(datei, sicherung)
            with open(datei, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=felder)
                w.writeheader()
                w.writerows(zeilen)

    if not args.schreiben:
        print("\nTrockenlauf — nichts geschrieben. Mit --schreiben übernehmen.")


if __name__ == "__main__":
    main()
"""
archiviere_version.py
---------------------
Kopiert die Ergebnisse einer Version nach evaluationsdaten/archiv/<VERSION>/:
  - alle Zeilen dieser Sitzungs-ID aus interaktionen.csv (mit dem csv-Modul, damit
    Antworten mit Zeilenumbrüchen vollständig bleiben — grep schneidet sie ab)
  - ragas_ergebnisse.csv und die ragas_*_details.csv (nur wenn sie zu dieser
    Version gehören: Prüfung der Spalte sitzungs_id in ragas_ergebnisse.csv)
  - lauf_<VERSION>.json und testlauf_retrieval_<VERSION>.csv, falls vorhanden

Start:  python archiviere_version.py V4-S2
"""
import csv
import shutil
import sys
from pathlib import Path

EVAL = Path("evaluationsdaten")


def main(version):
    ziel = EVAL / "archiv" / version
    ziel.mkdir(parents=True, exist_ok=True)

    with open(EVAL / "interaktionen.csv", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        zeilen = [z for z in r if z["sitzungs_id"] == version]
        felder = r.fieldnames
    with open(ziel / "interaktionen.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=felder)
        w.writeheader()
        w.writerows(zeilen)
    print(f"interaktionen.csv: {len(zeilen)} Zeilen")

    ergebnis = EVAL / "ragas_ergebnisse.csv"
    if ergebnis.exists():
        with open(ergebnis, encoding="utf-8", newline="") as f:
            ids = {z["sitzungs_id"] for z in csv.DictReader(f)}
        if ids == {version}:
            for p in EVAL.glob("ragas_*.csv"):
                shutil.copy2(p, ziel / p.name)
                print(f"kopiert: {p.name}")
        else:
            print(f"WARNUNG: ragas_ergebnisse.csv gehört zu {sorted(ids)}, nicht zu {version} -> nicht kopiert")
    for name in (f"lauf_{version}.json", f"testlauf_retrieval_{version}.csv"):
        if (EVAL / name).exists():
            shutil.copy2(EVAL / name, ziel / name)
            print(f"kopiert: {name}")
    print(f"Archiv: {ziel}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Aufruf: python archiviere_version.py <VERSION>")
    main(sys.argv[1])

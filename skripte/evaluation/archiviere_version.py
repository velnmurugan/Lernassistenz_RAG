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
        python archiviere_version.py V4-S2 V4-S2_J-v1   (eigener Archivordner, z. B. nach erneuter
                                                         Bewertung mit anderen Richter-Prompts)
"""
import sys as _sys, pathlib as _pl  # Projektpfade (lernassistent/pfadsetup.py)
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import csv
import shutil
import sys
from pathlib import Path

EVAL = Path("evaluationsdaten")


def main(version, ordner=None):
    ziel = EVAL / "archiv" / (ordner or version)
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
    if len(sys.argv) not in (2, 3):
        sys.exit("Aufruf: python archiviere_version.py <VERSION> [<ARCHIVORDNER>]")
    main(*sys.argv[1:])

"""
vergleiche_laeufe.py
--------------------
Prüft, ob zwei Läufe mit gleichem Generierungs-Prompt dieselben Chunks und dieselbe
Lösung liefern (Determinismus-Check, z. B. V4-S2 vs. V5-S2H: Aufruf 1 ist identisch).
Liest mit dem csv-Modul (mehrzeilige Felder werden korrekt gelesen).

Start:  python vergleiche_laeufe.py V4-S2 V5-S2H
"""
import csv
import sys
from pathlib import Path

EVAL = Path("evaluationsdaten")


def lade(version):
    for pfad in (EVAL / "archiv" / version / "interaktionen.csv", EVAL / "interaktionen.csv"):
        if pfad.exists():
            with open(pfad, encoding="utf-8") as f:
                zeilen = [z for z in csv.DictReader(f) if z["sitzungs_id"] == version]
            if zeilen:
                return {z["frage"]: z for z in zeilen}
    return {}


def main(a, b):
    la, lb = lade(a), lade(b)
    print(f"{a}: {len(la)} Fragen, {len(lb)} Fragen in {b}")
    spalte_chunks = next((s for s in ("quellen_ids", "top_ids", "quellen") if s in next(iter(la.values()), {})), None)
    gleich_c = gleich_l = n = 0
    for i, (frage, za) in enumerate(la.items(), 1):
        zb = lb.get(frage)
        if not zb:
            continue
        n += 1
        c = spalte_chunks and za[spalte_chunks] == zb[spalte_chunks]
        l = za["loesung"].strip() == zb["loesung"].strip()
        gleich_c += bool(c)
        gleich_l += l
        if not (c and l):
            print(f"  {frage[:60]:<60} Chunks gleich: {bool(c)!s:<5} Lösung gleich: {l}")
    print(f"\nGemeinsame Fragen: {n}")
    print(f"Chunks identisch ({spalte_chunks}): {gleich_c}/{n}")
    print(f"Lösung identisch:  {gleich_l}/{n}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
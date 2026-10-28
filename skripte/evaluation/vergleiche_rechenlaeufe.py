"""V16: Rechenläufe nebeneinander. Je Fragensatz eine Tabelle Frage × Lauf (richtig / teilweise / nein + Prüfstatus) und eine Summe.
Start (aus ~/RAG):  python skripte/evaluation/vergleiche_rechenlaeufe.py V135 V15 V16 V16-OHNE   (sucht rechen_varianten_<Label>.csv,
rechen_varianten_N100R-<Label>.csv und rechen_varianten_RV2-<Label>.csv). Schreibt evaluationsdaten/vergleich_rechenlaeufe.csv."""
import sys, csv, os
csv.field_size_limit(10**9)
labels = sys.argv[1:]
saetze = [("RV-v1", "rechen_varianten_{}.csv"), ("N100-Rechnen", "rechen_varianten_N100R-{}.csv"), ("RV-v2 (neu)", "rechen_varianten_RV2-{}.csv")]
zeilen_aus = []
for name, muster in saetze:
    daten = {}
    for l in labels:
        p = os.path.join("evaluationsdaten", muster.format(l))
        if os.path.exists(p):
            daten[l] = {r["nr"]: r for r in csv.DictReader(open(p, encoding="utf-8"))}
    if not daten:
        continue
    nrn = sorted({n for d in daten.values() for n in d}, key=lambda x: (x[0], int("".join(c for c in x if c.isdigit()) or 0)))
    print(f"\n=== {name} ===")
    print("Frage  " + "".join(f"{l:>22}" for l in daten))
    for n in nrn:
        zelle = []
        for l, d in daten.items():
            r = d.get(n)
            k = "-" if not r else {"ja": "OK", "teilweise": "teilw", "nein": "x"}.get(r["richtig"], r["richtig"]) + (f" {r['rechen_pruefung']}" if r and r["rechen_pruefung"] else "")
            zelle.append(k)
            zeilen_aus.append({"satz": name, "nr": n, "lauf": l, "richtig": r["richtig"] if r else "", "pruefung": r["rechen_pruefung"] if r else "",
                               "sekunden": r["sekunden"] if r else ""})
        print(f"{n:6} " + "".join(f"{z[:21]:>22}" for z in zelle))
    print("Summe  " + "".join(f"{sum(r['richtig'] == 'ja' for r in d.values()):>17} / {len(d):<2}" for d in daten.values()))
    print("Zeit   " + "".join(f"{sum(float(r['sekunden'] or 0) for r in d.values()) / 60:>18.0f} min" for d in daten.values()))
with open("evaluationsdaten/vergleich_rechenlaeufe.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["satz", "nr", "lauf", "richtig", "pruefung", "sekunden"]); w.writeheader(); w.writerows(zeilen_aus)
print("\nDatei: evaluationsdaten/vergleich_rechenlaeufe.csv")

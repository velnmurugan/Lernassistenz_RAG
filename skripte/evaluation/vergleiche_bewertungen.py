"""
vergleiche_bewertungen.py  (Eval300: Richter vs. Claude vs. Vel)
----------------------------------------------------------------
Vergleicht bis zu drei Bewertungen derselben 300 x 2 Antworten:
  --richter  evaluationsdaten/eval300_richter_<LABEL>_<MODELL>.csv
  --claude   ausgefüllter Bewertungsbogen (xlsx) oder CSV mit Spalten id, bewertung_ohne, bewertung_mit
  --vel      ausgefüllter Bewertungsbogen (xlsx) oder CSV
Ausgabe: Punkte je Bewerter (je Arm und Satz), Übereinstimmung je Paar (exakt in %, Cohens Kappa auf den
Klassen korrekt/teilweise/falsch_oder_verweigert und binär korrekt vs. nicht korrekt), Konfusionsmatrix,
und eine CSV mit allen Abweichungen zum Nachsehen.
Start:  python skripte/evaluation/vergleiche_bewertungen.py --richter ... --claude ... --vel ... [--fragen daten/testfragen/fragen_eval300.csv]
"""
import argparse
import collections
import csv
from pathlib import Path

NORM = {"korrekt": "K", "teilweise": "T", "falsch": "F", "verweigert": "F",
        "ablehnung_ok": "A", "nicht_abgelehnt": "N",
        "KORREKT": "K", "TEILWEISE": "T", "FALSCH": "F", "VERWEIGERT": "F",
        "ABLEHNUNG_OK": "A", "NICHT_ABGELEHNT": "N"}
PUNKTE = {"K": 1.0, "T": 0.5, "F": 0.0}


def lade(pfad):
    p = Path(pfad)
    if p.suffix.lower() == ".xlsx":
        import openpyxl
        ws = openpyxl.load_workbook(p, read_only=True, data_only=True).worksheets[0]
        zeilen = list(ws.iter_rows(values_only=True))
        kopf = [str(k) for k in zeilen[0]]
        daten = [dict(zip(kopf, z)) for z in zeilen[1:] if z and z[0]]
    else:
        with open(p, encoding="utf-8") as f:
            daten = list(csv.DictReader(f))
    out = {}
    for d in daten:
        o = d.get("bewertung_ohne", d.get("urteil_ohne"))
        m = d.get("bewertung_mit", d.get("urteil_mit"))
        out[str(d["id"])] = (NORM.get(str(o).strip()) if o else None, NORM.get(str(m).strip()) if m else None)
    return out


def kappa(paare):
    paare = [(a, b) for a, b in paare if a is not None and b is not None]
    n = len(paare)
    if n == 0:
        return float("nan"), 0
    po = sum(a == b for a, b in paare) / n
    ca, cb = collections.Counter(a for a, _ in paare), collections.Counter(b for _, b in paare)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n ** 2
    return ((po - pe) / (1 - pe) if pe < 1 else 1.0), n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--richter")
    ap.add_argument("--claude")
    ap.add_argument("--vel")
    ap.add_argument("--fragen", default="daten/testfragen/fragen_eval300.csv")
    ap.add_argument("--out", default="evaluationsdaten/eval300_bewertervergleich")
    args = ap.parse_args()
    with open(args.fragen, encoding="utf-8") as f:
        fragen = {r["id"]: r for r in csv.DictReader(f)}
    bewerter = {n: lade(p) for n, p in (("Richter", args.richter), ("Claude", args.claude), ("Vel", args.vel)) if p}
    zeilen = []
    zeilen.append("Punkte je Bewerter (nur Fragen im Buch, K 1 / T 0,5 / F 0; nur ausgefüllte Zellen)")
    for name, b in bewerter.items():
        for satz in ("alle", "N100", "NEU100", "V4"):
            teile = []
            for i, seite in enumerate(("ohne", "mit")):
                w = [PUNKTE[v[i]] for k, v in b.items() if k in fragen and fragen[k]["typ"] != "ausserhalb"
                     and (satz == "alle" or fragen[k]["satz"] == satz) and v[i] in PUNKTE]
                teile.append(f"{seite} {100 * sum(w) / len(w):5.1f} % (n={len(w)})" if w else f"{seite} –")
            a = [v for k, v in b.items() if k in fragen and fragen[k]["typ"] == "ausserhalb" and (satz == "alle" or fragen[k]["satz"] == satz)]
            abl = "  außerhalb abgelehnt: " + " / ".join(f"{s} {sum(x[i] == 'A' for x in a)}/{sum(x[i] in ('A', 'N') for x in a)}"
                                                       for i, s in enumerate(("ohne", "mit"))) if a else ""
            zeilen.append(f"  {name:<8} {satz:<6} " + "   ".join(teile) + abl)
    zeilen.append("\nÜbereinstimmung je Paar (alle Antworten beider Arme, nur wo beide bewertet haben)")
    abweichungen = []
    namen = list(bewerter)
    for i in range(len(namen)):
        for j in range(i + 1, len(namen)):
            a, b = bewerter[namen[i]], bewerter[namen[j]]
            paare, paare_bin, matrix = [], [], collections.Counter()
            for k in fragen:
                for s, seite in enumerate(("ohne", "mit")):
                    x, y = (a.get(k) or (None, None))[s], (b.get(k) or (None, None))[s]
                    if x and y:
                        paare.append((x, y)); matrix[(x, y)] += 1
                        if x in PUNKTE and y in PUNKTE:
                            paare_bin.append((x == "K", y == "K"))
                        if x != y:
                            abweichungen.append({"paar": f"{namen[i]}-{namen[j]}", "id": k, "arm": seite,
                                                 namen[i]: x, namen[j]: y, "satz": fragen[k]["satz"],
                                                 "typ": fragen[k]["typ"], "frage": fragen[k]["frage"][:150]})
            k3, n = kappa(paare)
            k2, _ = kappa(paare_bin)
            exakt = 100 * sum(x == y for x, y in paare) / n if n else float("nan")
            zeilen.append(f"  {namen[i]} – {namen[j]}: n={n}, exakt {exakt:.1f} %, Kappa (Klassen) {k3:.2f}, "
                          f"Kappa (korrekt ja/nein) {k2:.2f}")
            klassen = ["K", "T", "F", "A", "N"]
            zeilen.append("      Zeilen " + namen[i] + ", Spalten " + namen[j] + ": " + "  ".join(klassen))
            for x in klassen:
                if any(matrix[(x, y)] for y in klassen):
                    zeilen.append(f"      {x}: " + "  ".join(f"{matrix[(x, y)]:>3}" for y in klassen))
    text = "\n".join(zeilen)
    Path(args.out + ".txt").write_text(text + "\n", encoding="utf-8")
    if abweichungen:
        felder = ["paar", "id", "arm", "satz", "typ", *namen, "frage"]
        with open(args.out + "_abweichungen.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=felder, extrasaction="ignore")
            w.writeheader()
            w.writerows(abweichungen)
    print(text)
    print(f"\n{args.out}.txt  |  {args.out}_abweichungen.csv")


if __name__ == "__main__":
    main()

"""
eval300_auswertung.py  (Eval300, Phase 3: Zusammenfassung + Bewertungsbogen)
------------------------------------------------------------------------------
Liest Antworten (Phase 1) und Richter-Urteile (Phase 2) und schreibt
  evaluationsdaten/eval300_zusammenfassung_<LABEL>.txt   Punkte (K = 1, T = 0,5) je Arm, Satz, Buch, Typ;
                                                          Ablehnungsquote außerhalb; Paarvergleich mit Vorzeichentest
  evaluationsdaten/eval300_bewertungsbogen_<LABEL>.xlsx  Bogen für die Handbewertung (Vel und Claude getrennt),
                                                          OHNE Richter-Urteile und OHNE Satzkennung (blind)
Start:  python skripte/evaluation/eval300_auswertung.py EVAL300-V11B [--richter-datei <csv>]
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401

import argparse
import collections
import csv
import glob
import math
from pathlib import Path

PUNKTE = {"KORREKT": 1.0, "TEILWEISE": 0.5, "FALSCH": 0.0, "VERWEIGERT": 0.0, "FORMATFEHLER": None, "FEHLT": None}


def lies(p):
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def vorzeichentest(besser, schlechter):
    n = besser + schlechter
    if n == 0:
        return 1.0
    k = min(besser, schlechter)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def zusammenfassung(fragen, urteile):
    zeilen = []
    def block(name, auswahl):
        if not auswahl:
            return
        teile = []
        for seite in ("ohne", "mit"):
            werte = [PUNKTE.get(urteile[q["id"]][f"urteil_{seite}"]) for q in auswahl]
            werte = [w for w in werte if w is not None]
            c = collections.Counter(urteile[q["id"]][f"urteil_{seite}"] for q in auswahl)
            score = 100 * sum(werte) / len(werte) if werte else float("nan")
            teile.append(f"{seite}: {score:5.1f} %  (K {c['KORREKT']} / T {c['TEILWEISE']} / F {c['FALSCH']} / V {c['VERWEIGERT']}"
                         + (f" / ? {c['FORMATFEHLER'] + c['FEHLT']}" if c['FORMATFEHLER'] + c['FEHLT'] else "") + ")")
        zeilen.append(f"{name:<28} n={len(auswahl):>3}  " + "   ".join(teile))
    buch = [q for q in fragen if q["typ"] != "ausserhalb" and q["id"] in urteile]
    zeilen.append("Punkte = K 1 / T 0,5 / F und V 0, nur Fragen im Buch (Richter-Urteile, vorläufig)\n")
    block("ALLE im Buch", buch)
    for satz in ("N100", "NEU100", "V4"):
        block(f"Satz {satz}", [q for q in buch if q["satz"] == satz])
    for b in ("Fischer", "Böge"):
        block(f"Buch {b}", [q for q in buch if q["buch"] == b])
    for t in sorted({q["typ"] for q in buch}):
        block(f"Typ {t}", [q for q in buch if q["typ"] == t])
    for satz in ("N100", "NEU100", "V4"):
        for t in sorted({q["typ"] for q in buch}):
            block(f"  {satz} / {t}", [q for q in buch if q["satz"] == satz and q["typ"] == t])
    # Paarvergleich
    besser = schlechter = gleich = 0
    for q in buch:
        po, pm = PUNKTE.get(urteile[q["id"]]["urteil_ohne"]), PUNKTE.get(urteile[q["id"]]["urteil_mit"])
        if po is None or pm is None:
            continue
        besser += pm > po; schlechter += pm < po; gleich += pm == po
    zeilen.append(f"\nPaarvergleich im Buch: mit RAG besser {besser}, schlechter {schlechter}, gleich {gleich}; "
                  f"Vorzeichentest p = {vorzeichentest(besser, schlechter):.4f}")
    aus = [q for q in fragen if q["typ"] == "ausserhalb" and q["id"] in urteile]
    for satz in ("alle", "N100", "NEU100", "V4"):
        sel = [q for q in aus if satz == "alle" or q["satz"] == satz]
        if sel:
            txt = "   ".join(f"{s}: {sum(urteile[q['id']][f'urteil_{s}'] == 'ABLEHNUNG_OK' for q in sel)}/{len(sel)} abgelehnt"
                           for s in ("ohne", "mit"))
            zeilen.append(f"Außerhalb ({satz}): {txt}")
    pr = [q["id"] for q in aus if urteile[q["id"]].get("hinweis")]
    if pr:
        zeilen.append(f"Außerhalb, Regel und Richter uneinig (von Hand prüfen): {', '.join(pr)}")
    return "\n".join(zeilen)


def bewertungsbogen(pfad, antworten):
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Bewertung"
    kopf = ["id", "buch", "typ", "frage", "referenz", "referenz_passage", "antwort_ohne", "antwort_mit",
            "bewertung_ohne", "bewertung_mit", "anmerkung"]
    ws.append(kopf)
    import re as _re
    sauber = lambda t: _re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", str(t or ""))
    for a in antworten:
        a = {k: sauber(v) for k, v in a.items()}
        ws.append([a["id"], a["buch"], a["typ"], a["frage"], a["referenz"], a.get("referenz_passage", "")[:3000],
                   a.get("antwort_ohne", ""), a.get("antwort_mit", ""), None, None, None])
    breiten = [7, 9, 11, 45, 45, 50, 60, 60, 14, 14, 30]
    for i, b in enumerate(breiten, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = b
    for row in ws.iter_rows():
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
            c.font = Font(name="Arial", size=9, bold=c.row == 1)
    for row in ws.iter_rows(min_row=2):
        for c in row[8:11]:
            c.fill = PatternFill("solid", fgColor="FFF2CC")
    dv = DataValidation(type="list", formula1='"korrekt,teilweise,falsch,verweigert,ablehnung_ok,nicht_abgelehnt"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"I2:J{len(antworten) + 1}")
    ws.freeze_panes = "D2"
    le = wb.create_sheet("Legende")
    for zeile in [
        "Bewertung je Antwort (Spalten I und J), gleiche Regel für beide Arme:",
        "korrekt: alle Kernaussagen der Referenz, keine falsche Aussage, Zahl, Einheit oder Rechnung.",
        "teilweise: alles Gesagte ist richtig, aber ein Teil der Kernaussage fehlt (reine Auslassung).",
        "falsch: mindestens ein falscher Fakt/Wert/Einheit/Rechenfehler, Widerspruch zur Referenz oder Kern verfehlt.",
        "verweigert: Antwort lehnt eine Buchfrage ab (zählt wie falsch).",
        "Fragen 'ausserhalb': ablehnung_ok (lehnt ab) oder nicht_abgelehnt (antwortet trotzdem).",
        "Punkte: korrekt 1, teilweise 0,5, sonst 0. Der Bogen enthält absichtlich keine Richter-Urteile und keine Satzkennung.",
        "Die Referenzpassage ist automatisch aus der angegebenen Buchseite (±3 Seiten) gewählt; maßgeblich ist die Referenz.",
    ]:
        le.append([zeile])
    le.column_dimensions["A"].width = 140
    wb.save(pfad)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--richter-datei", default=None)
    args = ap.parse_args()
    antworten = lies(Path("evaluationsdaten") / f"eval300_antworten_{args.label}.csv")
    rd = args.richter_datei or (sorted(glob.glob(f"evaluationsdaten/eval300_richter_{args.label}_*.csv")) or [None])[-1]
    bogen = Path("evaluationsdaten") / f"eval300_bewertungsbogen_{args.label}.xlsx"
    bewertungsbogen(bogen, antworten)
    print(f"Bewertungsbogen: {bogen}")
    if not rd:
        print("Keine Richter-Datei gefunden: nur Bogen geschrieben.")
        return
    urteile = {z["id"]: z for z in lies(rd)}
    text = f"Antworten: eval300_antworten_{args.label}.csv | Richter: {rd}\n\n" + zusammenfassung(antworten, urteile)
    out = Path("evaluationsdaten") / f"eval300_zusammenfassung_{args.label}.txt"
    out.write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"\n{out}")


if __name__ == "__main__":
    main()

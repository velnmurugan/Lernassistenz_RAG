"""
fuelle300.py  (Fragen300, Schritt 5: Bewertungsbogen füllen)
Trägt Antworten, Zeiten, Richterurteil (Bewertungsspalte 3, Begründung als Kommentar), Rang und Faithfulness in eine Kopie
des Bogens ein. Vorhandene Bewertungen 1 und 2 werden nie überschrieben. Fehlende Schritte bleiben leer.
  python skripte/evaluation/fuelle300.py F300-V20 daten/boegen/Fragen300_Bewertung.xlsx <Ziel.xlsx>
"""
import csv
import sys
from pathlib import Path

import openpyxl
from openpyxl.comments import Comment

label, vorlage, ziel = sys.argv[1:4]
NUR_ANTWORTEN = "--nur-antworten" in sys.argv  # verblindetes Bewertungsexemplar: keine Richterurteile, kein Rang, keine Faithfulness
E = Path("evaluationsdaten")


def lies(name):
    p = E / f"{name}_{label}.csv"
    return list(csv.DictReader(open(p, encoding="utf-8"))) if p.exists() else []


ant = {z["id"]: z for z in lies("antworten300")}
rang = {} if NUR_ANTWORTEN else {z["id"]: z for z in lies("rang300")}
richter = {} if NUR_ANTWORTEN else {(z["id"], z["seite"]): z for z in lies("richter300")}
faith = {} if NUR_ANTWORTEN else {(z["id"], z["seite"]): z for z in lies("faith300")}

# Gibt es den Zielbogen schon (evtl. mit Bewertungen 1/2), wird er weitergeführt statt aus der Vorlage neu erzeugt.
basis = ziel if Path(ziel).exists() else vorlage
wb = openpyxl.load_workbook(basis)
ws = wb["Fragen"]
SP = {c.value: c.column for c in ws[1]}
n = {"Antworten": 0, "Richter": 0, "Rang": 0, "Faithfulness": 0}


def zahl(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


for r in range(2, ws.max_row + 1):
    qid = ws.cell(r, 1).value
    a = ant.get(qid)
    if a:
        n["Antworten"] += 1
        ws.cell(r, SP["Antwort ohne RAG"]).value = a.get("antwort_ohne")
        ws.cell(r, SP["Ohne RAG: Zeit (s)"]).value = zahl(a.get("sek_ohne"))
        ws.cell(r, SP["Antwort mit RAG"]).value = a.get("antwort_mit")
        ws.cell(r, SP["Mit RAG: Zeit (s)"]).value = zahl(a.get("sek_mit"))
    for seite, spalte in (("ohne", "Ohne RAG: 3"), ("mit", "Mit RAG: 3")):
        j = richter.get((qid, seite))
        if j and j.get("urteil"):
            c = ws.cell(r, SP[spalte])
            c.value = j["urteil"]
            if j.get("begruendung"):
                c.comment = Comment(j["begruendung"][:600], "3")
            n["Richter"] += 1
        f = faith.get((qid, seite))
        if f and f.get("faithfulness") not in ("", None):
            ws.cell(r, SP[f"Faithfulness {seite} RAG"]).value = zahl(f["faithfulness"])
            n["Faithfulness"] += 1
    g = rang.get(qid)
    if g:
        ws.cell(r, SP["Mit RAG: Rang der Buchstelle"]).value = int(g["rang"])
        n["Rang"] += 1
wb.calculation.fullCalcOnLoad = True
try:
    wb.save(ziel)
except PermissionError:  # Datei in Excel geöffnet
    import time
    ziel = ziel.replace(".xlsx", f"_{time.strftime('%H%M')}.xlsx")
    wb.save(ziel)
    print("Hinweis: Bogen war geöffnet, neue Datei geschrieben")
print("Bogen:", ziel, "(weitergeführt)" if basis == ziel else "(aus Vorlage)", n)

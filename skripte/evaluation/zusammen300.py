"""
zusammen300.py  (Studie 1: menschliche Bewertungen in den automatisch gefüllten Bogen übernehmen)
Kopiert die Bewertungsspalten 1 und 2 (ohne und mit RAG) aus dem Bewertungsexemplar in den vom Lauf gefüllten Bogen
(Antworten, Richter, Rang, Faithfulness) und speichert das Ergebnis als neue Datei. Abgleich über die ID.
  python skripte/evaluation/zusammen300.py <Bewertungsexemplar.xlsx> <Lauf-Bogen.xlsx> <Ziel.xlsx>
"""
import sys
import openpyxl

bew, lauf, ziel = sys.argv[1:4]
SPALTEN = ["Ohne RAG: 1", "Ohne RAG: 2", "Mit RAG: 1", "Mit RAG: 2"]
quelle = openpyxl.load_workbook(bew, data_only=False)["Fragen"]
qsp = {c.value: c.column for c in quelle[1]}
werte = {}
for r in range(2, quelle.max_row + 1):
    qid = quelle.cell(r, 1).value
    if qid:
        werte[qid] = {s: quelle.cell(r, qsp[s]).value for s in SPALTEN}
wb = openpyxl.load_workbook(lauf)
ws = wb["Fragen"]
sp = {c.value: c.column for c in ws[1]}
n = {s: 0 for s in SPALTEN}
for r in range(2, ws.max_row + 1):
    w = werte.get(ws.cell(r, 1).value, {})
    for s in SPALTEN:
        if w.get(s) not in (None, ""):
            ws.cell(r, sp[s]).value = w[s]
            n[s] += 1
wb.calculation.fullCalcOnLoad = True
wb.save(ziel)
print("Zusammengeführt:", ziel, n)

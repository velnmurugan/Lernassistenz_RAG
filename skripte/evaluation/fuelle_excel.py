"""Trägt die Antworten (ohne / mit RAG) aus einer eval300_antworten_*.csv in eine Kopie des Bewertungsbogens ein.
Aufruf: python fuelle_excel.py <antworten.csv> <vorlage.xlsx> <ausgabe.xlsx>"""
import csv, re, sys
import openpyxl
ILL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
antworten, vorlage, ausgabe = sys.argv[1:4]
A = {r["id"]: r for r in csv.DictReader(open(antworten, encoding="utf-8"))}
wb = openpyxl.load_workbook(vorlage)
ws = wb["Questions"]
kopf = [c.value for c in ws[1]]
c_ohne = kopf.index("Answer WITHOUT RAG") + 1
c_mit = kopf.index("Answer WITH RAG") + 1
n = fehlt = 0
for row in range(2, ws.max_row + 1):
    i = ws.cell(row, 1).value
    if not i: continue
    a = A.get(i)
    if not a or not a.get("antwort_ohne") or not a.get("antwort_mit"):
        fehlt += 1
        if not a: continue
    ws.cell(row, c_ohne).value = ILL.sub(" ", a.get("antwort_ohne", ""))
    ws.cell(row, c_mit).value = ILL.sub(" ", a.get("antwort_mit", ""))
    n += 1
wb.save(ausgabe)
print(f"{n} Zeilen eingetragen, {fehlt} unvollständig -> {ausgabe}")
sys.exit(0 if fehlt == 0 else 1)

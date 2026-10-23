"""Diagnose: Warum markiert der Richter korrekte Antworten als 'ausweichend'?
Nimmt die Vergleichs-CSV (antwort_mit, hand_mit) + RAGAS-Log (Flag je Frage), ruft den Richter mit
dem J-v1-Prompt erneut auf und druckt die BEGRÜNDUNG. Nur lesend, ändert nichts.
Aufruf (im Projektordner ~/RAG):
  python skripte/evaluation/pruefe_ausweichend.py evaluationsdaten/vergleich_rag_RAGVGL-N100F-V10A_vorbewertet.csv evaluationsdaten/ragas_N100F_V10A.log 12
"""
import sys, re, csv, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ragas_auswertung as ra

csv_pfad, log_pfad = sys.argv[1], sys.argv[2]
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 12
zeilen = {int(z["nr"]): z for z in csv.DictReader(open(csv_pfad, encoding="utf-8"))}
flag = {}
for l in open(log_pfad, encoding="utf-8"):
    m = re.match(r"F(\d+)\s", l)
    if m and "[Verweigerung]" not in l:
        flag[int(m.group(1))] = "ausweichend" in l
ziel = [n for n, f in flag.items() if f and zeilen[n]["hand_mit"] == "korrekt"][:limit]
print(f"{len(ziel)} Fälle: markiert 'ausweichend', von Hand 'korrekt'. Richter: {ra.JUDGE_MODELL_STANDARD}\n")
for n in ziel:
    z = zeilen[n]
    prompt = f"""Prüfe, ob die Antwort das Gefragte liefert. AUSWEICHEND = JA, wenn sie das Gefragte nicht liefert, z. B.
weil sie allgemein bleibt, obwohl ein bestimmter Wert, eine Liste oder ein Vorgehen gefragt ist.
Ob die Antwort richtig ist, spielt keine Rolle.

### Frage
{z['frage']}

### Antwort
{z['antwort_mit']}

Antworte genau in diesem Format:
BEGRÜNDUNG: <ein Satz>
AUSWEICHEND: JA oder NEIN"""
    roh = ra.richter(prompt, ra.JUDGE_MODELL_STANDARD)
    print(f"--- nr {n} ({z['typ']}) ---\nFrage: {z['frage'][:140]}\nAntwort: {z['antwort_mit'][:200].replace(chr(10),' ')}\nRichter: {roh.strip()}\n")
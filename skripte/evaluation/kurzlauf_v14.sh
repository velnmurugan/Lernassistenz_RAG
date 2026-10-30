#!/usr/bin/env bash
# V14b Kurzlauf (ca. 1 h, nur Rechnen, ein Arm: RP-v11 + Rechenweg mit Python). Vergleich mit den vorhandenen V134-Ergebnissen.
# 1) Probe auf R12: erst RW-v2 (Werkzeugaufruf über Ollama), wenn das Modell das Werkzeug nicht aufruft, RW-v3 (Platzhalter
#    [[Name = Ausdruck]], Python setzt die Zahlen ein). Die erste Variante, die genutzt wird, gilt für den Rest.
# 2) 22 N100-Rechenfragen. 3) 8 RV-Fragen, die in V134 falsch waren.
# Start (aus ~/RAG, pilot_rag, nur Ollama läuft):
#   bash skripte/evaluation/kurzlauf_v14.sh 2>&1 | tee protokolle/kurzlauf_v14_$(date +%Y%m%d_%H%M).txt
cd "$(dirname "$0")/../.." || exit 1
mkdir -p protokolle
export PYTHONUNBUFFERED=1 LERNASSISTENT_RP=RP-v11 LERNASSISTENT_G=G-v5 LERNASSISTENT_FS=FS-v3 LERNASSISTENT_CTX=8192
python skripte/evaluation/teste_v14_offline.py | tail -1
genutzt () {  # $1 Label: 0, wenn die Probe das Werkzeug genutzt hat
  python - "$1" <<'PY'
import csv, sys; csv.field_size_limit(10**9)
x = list(csv.DictReader(open(f"evaluationsdaten/rechen_varianten_{sys.argv[1]}.csv", encoding="utf-8")))[0]
print("   Werkzeug:", x["werkzeug"], "| Aufrufe:", x["werkzeug_protokoll"][:400])
sys.exit(0 if " genutzt" in x["werkzeug"] and not x["werkzeug"].endswith(" 0 Aufrufe") else 1)
PY
}
RW=""
for v in RW-v2 RW-v3; do
  echo "=== Probe $v (R12) $(date +%H:%M) ==="
  rm -f "evaluationsdaten/rechen_varianten_V14K-PROBE-$v.csv"
  LERNASSISTENT_RW=$v python skripte/evaluation/teste_rechen_varianten.py "V14K-PROBE-$v" --nur R12 2>&1 | grep "^R12"
  if genutzt "V14K-PROBE-$v"; then RW=$v; break; fi
done
[ -n "$RW" ] || { echo "ABBRUCH: weder RW-v2 noch RW-v3 genutzt. Ausgabe bitte schicken."; exit 1; }
export LERNASSISTENT_RW=$RW
echo "=> verwendet: $RW"
echo; echo "=== N100-Rechenfragen (22) mit $RW $(date +%H:%M) ==="
rm -f evaluationsdaten/rechen_varianten_N100R-V14K.csv
python skripte/evaluation/teste_rechen_varianten.py N100R-V14K --fragen daten/testfragen/n100_rechnung_v1.csv 2>&1 | tee protokolle/rechen_varianten_N100R-V14K.txt
echo; echo "=== RV, 8 in V134 falsche Fragen, mit $RW $(date +%H:%M) ==="
rm -f evaluationsdaten/rechen_varianten_V14K.csv
python skripte/evaluation/teste_rechen_varianten.py V14K --nur R01,R02,R04,R12,R14,R17,R19,R20 2>&1 | tee protokolle/rechen_varianten_V14K.txt
python -m zipfile -c V14K_ergebnisse.zip evaluationsdaten/rechen_varianten_V14K-PROBE-*.csv evaluationsdaten/rechen_varianten_{N100R-V14K,V14K}.csv \
  protokolle/rechen_varianten_{N100R-V14K,V14K}.txt $(ls -t protokolle/kurzlauf_v14_*.txt 2>/dev/null | head -1) \
  && cp V14K_ergebnisse.zip "$(bash "$HOME/RAG/skripte/werkzeuge/windows_downloads.sh")/" 2>/dev/null
echo "Ergebnis-Zip: ~/RAG/V14K_ergebnisse.zip (auch in Windows-Downloads)"
echo "=== fertig $(date +%H:%M) ==="

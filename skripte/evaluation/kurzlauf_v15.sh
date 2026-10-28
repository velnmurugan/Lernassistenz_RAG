#!/usr/bin/env bash
# V15 Lauf (ca. 80 min, nur Rechnen): RP-v11 + RB-v7 (Nachrechnung rechnet Einheiten in Grundeinheiten um), ohne Rechenwerkzeug.
# Vergleich mit dem Basislauf V135 (gleiche Fragen, RB-v6). 22 RV-Fragen + 22 N100-Rechenfragen.
# Start (aus ~/RAG, pilot_rag, nur Ollama läuft):
#   bash skripte/evaluation/kurzlauf_v15.sh 2>&1 | tee protokolle/kurzlauf_v15_$(date +%Y%m%d_%H%M).txt
cd "$(dirname "$0")/../.." || exit 1
mkdir -p protokolle
export PYTHONUNBUFFERED=1 LERNASSISTENT_RP=RP-v11 LERNASSISTENT_G=G-v5 LERNASSISTENT_FS=FS-v3 LERNASSISTENT_CTX=8192 LERNASSISTENT_RW= LERNASSISTENT_RB=RB-v7
python skripte/evaluation/teste_v15_offline.py | tail -1
echo "=== RV (22), RB-v7 $(date +%H:%M) ==="
rm -f evaluationsdaten/rechen_varianten_V15.csv
python skripte/evaluation/teste_rechen_varianten.py V15 2>&1 | tee protokolle/rechen_varianten_V15.txt
echo; echo "=== N100-Rechenfragen (22), RB-v7 $(date +%H:%M) ==="
rm -f evaluationsdaten/rechen_varianten_N100R-V15.csv
python skripte/evaluation/teste_rechen_varianten.py N100R-V15 --fragen daten/testfragen/n100_rechnung_v1.csv 2>&1 | tee protokolle/rechen_varianten_N100R-V15.txt
dateien="evaluationsdaten/rechen_varianten_V15.csv evaluationsdaten/rechen_varianten_N100R-V15.csv protokolle/rechen_varianten_V15.txt protokolle/rechen_varianten_N100R-V15.txt"
for x in evaluationsdaten/rechen_varianten_V135.csv evaluationsdaten/rechen_varianten_N100R-V135.csv protokolle/rechen_varianten_V135.txt protokolle/rechen_varianten_N100R-V135.txt; do [ -f "$x" ] && dateien="$dateien $x"; done
python -m zipfile -c V15_ergebnisse.zip $dateien $(ls -t protokolle/kurzlauf_v15_*.txt 2>/dev/null | head -1) \
  && cp V15_ergebnisse.zip "/mnt/c/Users/Vel Narayanasamy/Downloads/" 2>/dev/null
echo "Ergebnis-Zip: ~/RAG/V15_ergebnisse.zip (auch in Windows-Downloads; enthält V135, falls vorhanden)"
echo "=== fertig $(date +%H:%M) ==="

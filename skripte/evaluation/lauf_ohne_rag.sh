#!/usr/bin/env bash
# Rechenfragen OHNE RAG (ca. 30–40 min): RV-v1 (22), RV-v2 (21). N100 nicht (schon geprüft). Vordergrund, kein nohup.
# Start (aus ~/RAG, pilot_rag, nur Ollama läuft):
#   bash skripte/evaluation/lauf_ohne_rag.sh 2>&1 | tee protokolle/ohne_rag_$(date +%Y%m%d_%H%M).txt
cd "$(dirname "$0")/../.." || exit 1
mkdir -p protokolle evaluationsdaten
export PYTHONUNBUFFERED=1 LERNASSISTENT_CTX=8192
for x in "RV1-OHNERAG daten/testfragen/rechen_varianten_v1.csv" "RV2-OHNERAG daten/testfragen/rechen_varianten_v2.csv"; do
  set -- $x
  echo; echo "=== $1 $(date +%H:%M) ==="
  rm -f "evaluationsdaten/ohne_rag_$1.csv"
  python skripte/evaluation/lauf_ohne_rag.py "$1" --fragen "$2"
done
python -m zipfile -c OHNERAG_ergebnisse.zip evaluationsdaten/ohne_rag_*OHNERAG.csv $(ls -t protokolle/ohne_rag_*.txt 2>/dev/null | head -1) \
  && cp OHNERAG_ergebnisse.zip "$(bash "$HOME/RAG/skripte/werkzeuge/windows_downloads.sh")/" 2>/dev/null
echo "Ergebnis-Zip: ~/RAG/OHNERAG_ergebnisse.zip (auch in Windows-Downloads)"
echo "=== fertig $(date +%H:%M) ==="

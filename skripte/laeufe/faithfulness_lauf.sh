#!/usr/bin/env bash
# Faithfulness mit und ohne Retrieval (N100, V11B, 95 Fragen). Vordergrund, kein nohup. Aufruf aus ~/RAG: bash skripte/laeufe/faithfulness_lauf.sh [probe]
cd "$(dirname "$0")/../.." || exit 1
mkdir -p protokolle evaluationsdaten
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
for f in daten/wissensbasen/knowledge_base_fischer_boege_v7r.json evaluationsdaten/vergleich_rag_RAGVGL-N100F-V11B-BEIDE7.csv evaluationsdaten/vergleich_rag_RAGVGL-N100B-V11B-BEIDE7.csv skripte/evaluation/ragas_auswertung.py; do
  [ -f "$f" ] || { echo "FEHLT: $f"; exit 1; }
done
ollama list | grep -q "mistral-nemo" || { echo "FEHLT: Richtermodell mistral-nemo (ollama pull mistral-nemo)"; exit 1; }
for m in $(ollama ps 2>/dev/null | awk 'NR>1{print $1}'); do ollama stop "$m"; done
echo "=== Start $(date +%H:%M) ==="; ollama ps
ARG=""; [ "$1" = "probe" ] && ARG="--limit 3"
python skripte/evaluation/faithfulness_rag_vs_ohne.py $ARG 2>&1 | tee "protokolle/faithfulness_$(date +%Y%m%d_%H%M).txt"
dateien=""
for x in evaluationsdaten/faithfulness_rag_vs_ohne_V11B.csv evaluationsdaten/faithfulness_rag_vs_ohne_V11B_details.csv evaluationsdaten/faithfulness_rag_vs_ohne_V11B_zusammenfassung.txt $(ls -t protokolle/faithfulness_*.txt | head -1); do [ -f "$x" ] && dateien="$dateien $x"; done
python -m zipfile -c faithfulness_ergebnisse.zip $dateien && cp faithfulness_ergebnisse.zip "$(bash "$HOME/RAG/skripte/werkzeuge/windows_downloads.sh")/" 2>/dev/null
echo "Ergebnis-Zip: ~/RAG/faithfulness_ergebnisse.zip (auch in Windows-Downloads)"
echo "=== fertig $(date +%H:%M) ==="

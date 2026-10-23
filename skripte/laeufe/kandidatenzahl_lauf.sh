#!/usr/bin/env bash
# Retrieval-only test of the reranker candidate count (50/35/25) on the merged KB, development questions only.
# Start (project folder, env pilot_rag active):
#   bash skripte/laeufe/kandidatenzahl_lauf.sh 2>&1 | tee protokolle/kandidatenzahl_$(date +%Y%m%d_%H%M).txt
# Duration: about 3 x 13 s per question at 50 candidates, less at 35/25; roughly 25-30 min for ~55 questions.
cd "$(dirname "$0")/../.." || exit 1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
KB=daten/wissensbasen/knowledge_base_fischer_boege.json
F_ROH=daten/testfragen/testfragen_fischer_v1.csv
F_CHUNKS=daten/testfragen/testfragen_fischer_v1_chunks_beide.csv
B_FRAGEN=daten/testfragen/testfragen_v1.csv
[ -f "$KB" ] || { echo "Missing: $KB"; exit 1; }
python skripte/wissensbasis/ordne_chunks_zu.py "$F_ROH" "$KB" "$F_CHUNKS" | tail -5
python skripte/evaluation/teste_kandidatenzahl.py --kb "$KB" --fragen "$F_CHUNKS" "$B_FRAGEN" \
    --namen Fischer Boege --kandidaten 50 35 25 --rrf-k 5

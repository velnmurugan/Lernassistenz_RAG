#!/usr/bin/env bash
# Neue Böge-Extraktion (MinerU): Register entfernen, mit Fischer v7c kombinieren, Gold-Chunks beider N100-Sets
# neu zuordnen, N100 gegen die neue kombinierte Wissensbasis laufen lassen (gleiche Version wie V10a).
# Start (Projektordner, pilot_rag aktiv):
#   bash skripte/laeufe/n100_beide_v7_lauf.sh V10A 2>&1 | tee protokolle/n100_beide_v7_V10A_$(date +%Y%m%d_%H%M).txt
# Dauer: Vorbereitung wenige Minuten, Einbetten der Wissensbasis einmalig, dann ca. 70 min. Nichts Vorhandenes wird überschrieben.
LABEL="${1:?Versionskennung angeben, z. B. V10A}"
cd "$(dirname "$0")/../.." || exit 1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
RET="--retrieval hybrid_kg_rr --rrf-k 5"
WB=daten/wissensbasen
KB_F=$WB/knowledge_base_fischer_v7c.json
KB_B_ROH=$WB/knowledge_base_boege_v7b.json
KB_B=$WB/knowledge_base_boege_v7b_ohne_register.json
KB_B_ALT=$WB/knowledge_base_boege.json
KB=$WB/knowledge_base_fischer_boege_v7r.json
F_ROH=daten/testfragen/testfragen_fischer_v2.csv
F_CHUNKS=daten/testfragen/testfragen_fischer_v2_chunks_beide_v7r.csv
B_ROH=daten/testfragen/testfragen_boege_v2.csv
B_FRAGEN=daten/testfragen/testfragen_boege_v2_v7r.csv

echo "=== 1 Register entfernen"
python skripte/wissensbasis/entferne_register.py "$KB_B_ROH" "$KB_B" || exit 1
echo "=== 2 Kombinierte Wissensbasis (neu)"
python skripte/wissensbasis/baue_kombinierte_wissensbasis.py "$KB_F" Fischer "$KB_B" Böge "$KB" || exit 1
echo "=== 3 Gold-Chunks neu zuordnen"
python skripte/wissensbasis/ordne_chunks_zu.py "$F_ROH" "$KB" "$F_CHUNKS" | tail -8
python skripte/wissensbasis/ordne_boege_alt_neu.py "$B_ROH" "$KB_B_ALT" "$KB" "$B_FRAGEN" | tail -40
echo "=== N100F-$LABEL-BEIDE7"
python skripte/evaluation/fuehre_testfragen_aus.py "N100F-$LABEL-BEIDE7" $RET --kb "$KB" --fragen "$F_CHUNKS"
echo "=== N100B-$LABEL-BEIDE7"
python skripte/evaluation/fuehre_testfragen_aus.py "N100B-$LABEL-BEIDE7" $RET --kb "$KB" --fragen "$B_FRAGEN"
ls -1 evaluationsdaten/testlauf_retrieval_N100*-"$LABEL"-BEIDE7.csv 2>/dev/null

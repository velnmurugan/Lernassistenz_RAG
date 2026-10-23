#!/usr/bin/env bash
# N100 gegen die KOMBINIERTE Wissensbasis (beide Bücher in einem Index), gleiche Version/Einstellungen wie V10a.
# Prüft, ob die Mischung Recall/Verweigerung/Antwortqualität verschlechtert.
# Start (im Projektordner, Umgebung pilot_rag aktiv):
#   bash skripte/laeufe/n100_beide_lauf.sh V10A 2>&1 | tee protokolle/n100_beide_V10A_$(date +%Y%m%d_%H%M).txt
# Dauer wie der erste N100-Lauf (ca. 70 min), plus einmaliges Einbetten der Wissensbasis beim ersten Start.
LABEL="${1:?Versionskennung angeben, z. B. V10A}"
cd "$(dirname "$0")/../.." || exit 1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
RET="--retrieval hybrid_kg_rr --rrf-k 5"
KB=daten/wissensbasen/knowledge_base_fischer_boege.json
F_ROH=daten/testfragen/testfragen_fischer_v2.csv
F_CHUNKS=daten/testfragen/testfragen_fischer_v2_chunks_beide.csv
B_FRAGEN=daten/testfragen/testfragen_boege_v2.csv
[ -f "$KB" ] || { echo "Fehlt: $KB (erst baue_kombinierte_wissensbasis.py ausführen)"; exit 1; }
echo "=== Chunk-Zuordnung Fischer gegen kombinierte KB"
python skripte/wissensbasis/ordne_chunks_zu.py "$F_ROH" "$KB" "$F_CHUNKS" | tail -8
echo "=== N100F-$LABEL-BEIDE"
python skripte/evaluation/fuehre_testfragen_aus.py "N100F-$LABEL-BEIDE" $RET --kb "$KB" --fragen "$F_CHUNKS"
echo "=== N100B-$LABEL-BEIDE"
python skripte/evaluation/fuehre_testfragen_aus.py "N100B-$LABEL-BEIDE" $RET --kb "$KB" --fragen "$B_FRAGEN"
ls -1 evaluationsdaten/testlauf_retrieval_N100*-"$LABEL"-BEIDE.csv 2>/dev/null

#!/usr/bin/env bash
# Vergleichs-App ohne/mit RAG (Stand V20), Port 8503. Aus ~/RAG, pilot_rag aktiv, Ollama läuft:
#   bash skripte/laeufe/start_vergleich.sh
cd "${DEMO_ROOT:-$PWD}" || exit 1
[ -f app.py ] || { echo "Bitte aus ~/RAG starten"; exit 1; }
[ -f skripte/evaluation/eval300_antworten.py ] || { echo "FEHLER: skripte/evaluation/eval300_antworten.py fehlt"; exit 1; }
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
unset LERNASSISTENT_HG LERNASSISTENT_THINK
export LERNASSISTENT_G=G-v6 LERNASSISTENT_RP=RP-v13 LERNASSISTENT_RB=RB-v8 LERNASSISTENT_FS=FS-v3 \
       LERNASSISTENT_V18=ADEK LERNASSISTENT_V19=AB LERNASSISTENT_CTX=8192 LERNASSISTENT_RW= \
       LERNASSISTENT_KB=daten/wissensbasen/knowledge_base_fischer_boege_v7r.json LERNASSISTENT_RETRIEVAL=hybrid_kg_rr
streamlit run skripte/evaluation/vergleich_app.py --server.port 8503 --server.fileWatcherType none

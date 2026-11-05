#!/usr/bin/env bash
# Lern-App V21-S (schnell): Antworten wie V20, Reranker auf der GPU, Hinweis zuerst. Port 8501 (gleicher Link wie bisher).
# Aus ~/RAG, pilot_rag aktiv, Ollama läuft:  bash skripte/laeufe/start_schnell.sh
cd "${DEMO_ROOT:-$PWD}" || exit 1
[ -f app.py ] || { echo "Bitte aus ~/RAG starten"; exit 1; }
grep -q "# V21-S" lernassistent/reranker.py || { echo "FEHLER: V21-S nicht eingespielt (python ~/v21s/patch_v21s.py)"; exit 1; }
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
unset LERNASSISTENT_HG LERNASSISTENT_THINK
export LERNASSISTENT_G=G-v6 LERNASSISTENT_RP=RP-v13 LERNASSISTENT_RB=RB-v8 LERNASSISTENT_FS=FS-v3 \
       LERNASSISTENT_V18=ADEK LERNASSISTENT_V19=AB LERNASSISTENT_CTX=8192 LERNASSISTENT_RW= \
       LERNASSISTENT_KB=daten/wissensbasen/knowledge_base_fischer_boege_v7r.json LERNASSISTENT_RETRIEVAL=hybrid_kg_rr \
       LERNASSISTENT_RR_GPU=1 LERNASSISTENT_HINWEIS_ZUERST=1
streamlit run app.py --server.fileWatcherType none "$@"

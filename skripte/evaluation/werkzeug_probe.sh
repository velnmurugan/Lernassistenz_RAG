#!/usr/bin/env bash
# V14 Probe (ca. 10 min, Vordergrund): kann qwen3.5:9b über Ollama das Rechenwerkzeug aufrufen? 3 RV-Fragen mit RW-v1.
# Start (aus ~/RAG, pilot_rag, Ollama läuft):  bash skripte/evaluation/werkzeug_probe.sh
cd "$(dirname "$0")/../.." || exit 1
mkdir -p protokolle
export PYTHONUNBUFFERED=1 LERNASSISTENT_RP=RP-v11 LERNASSISTENT_G=G-v5 LERNASSISTENT_FS=FS-v3 LERNASSISTENT_CTX=8192 LERNASSISTENT_RW=RW-v1
echo "Ollama: $(curl -s localhost:11434/api/version 2>/dev/null || echo 'nicht erreichbar über localhost')"
rm -f evaluationsdaten/rechen_varianten_V14PROBE.csv
python skripte/evaluation/teste_rechen_varianten.py V14PROBE --nur R12,R20,R04 2>&1 | tee protokolle/werkzeug_probe.txt
python - <<'PY'
import csv; csv.field_size_limit(10**9)
for x in csv.DictReader(open("evaluationsdaten/rechen_varianten_V14PROBE.csv", encoding="utf-8")):
    print(f"\n== {x['nr']} {x['richtig']} | {x['werkzeug']}\n   Aufrufe: {x['werkzeug_protokoll'][:600]}\n   Lösung: {x['loesung'][:300]}")
PY

#!/usr/bin/env bash
# Studie 1, Bedingung D: OpenAI-Modell MIT RAG (Suche + Prompt wie V20, ein API-Aufruf je Frage).
# Umgebung aktiv. Ollama wird nicht gebraucht. Schlüssel: export OPENAI_API_KEY='sk-...'
#   bash skripte/laeufe/lauf_gpt_rag300.sh test     # Offline-Selbsttest (ohne Schlüssel, Sekunden)
#   bash skripte/laeufe/lauf_gpt_rag300.sh prompt   # 5 Prompts + Größe + Kostenschätzung, KEIN API-Aufruf
#   bash skripte/laeufe/lauf_gpt_rag300.sh pilot    # 10 Fragen an die API (nur Funktionsprobe)
#   bash skripte/laeufe/lauf_gpt_rag300.sh q100     # Q1–Q100
#   bash skripte/laeufe/lauf_gpt_rag300.sh alles    # alle 300
# Jeder Lauf setzt nach Abbruch fort (gleicher Befehl). Zip mit Ergebnis nach $RUN300_ZIEL (Standard: ausgabe/).
cd "${RUN300_ROOT:-$(dirname "$0")/../..}" || exit 1
[ -d lernassistent ] || { echo "Ordner lernassistent fehlt"; exit 1; }
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
unset LERNASSISTENT_HG LERNASSISTENT_THINK
export LERNASSISTENT_G=G-v6 LERNASSISTENT_RP=RP-v13 LERNASSISTENT_RB=RB-v8 LERNASSISTENT_FS=FS-v3 LERNASSISTENT_RW=
LABEL="${GPTRAG_LABEL:-F300-GPT61SOL-RAG}"
MODELL="${GPTRAG_MODELL:-gpt-6.1-sol}"
ZIEL="${RUN300_ZIEL:-ausgabe}"
EV=skripte/evaluation
mkdir -p protokolle evaluationsdaten "$ZIEL"
cmd="${1:?test | prompt | pilot | q100 | alles}"
LOG="protokolle/gptrag300_${cmd}_$(date +%Y%m%d_%H%M).txt"
zippen() {
  python - "$LABEL" "$ZIEL" "$LOG" <<'PY'
import sys, zipfile, time
from pathlib import Path
label, ziel, log = sys.argv[1:4]
z = Path(ziel) / f"gptrag300_{label}_{time.strftime('%Y%m%d_%H%M')}.zip"
with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as f:
    for p in [Path(f"evaluationsdaten/gptrag300_{label}.csv"), Path(f"evaluationsdaten/gptrag300_{label}_konfig.txt"), Path(log)]:
        if p.exists():
            f.write(p, p.as_posix())
print("Zip:", z)
PY
}
[ "$cmd" = test ] || [ "$cmd" = prompt ] || [ -n "$OPENAI_API_KEY" ] || { echo "FEHLER: export OPENAI_API_KEY='sk-...' fehlt"; exit 1; }
case "$cmd" in
  test)   python "$EV/teste_gpt_rag300.py" 2>&1 | tee -a "$LOG" ;;
  prompt) python "$EV/gpt_rag300.py" --nur-prompt --limit 5 --modell "$MODELL" 2>&1 | tee -a "$LOG" ;;
  pilot)  python "$EV/gpt_rag300.py" --label "$LABEL-PILOT" --limit 10 --modell "$MODELL" 2>&1 | tee -a "$LOG" ;;
  q100)   python "$EV/gpt_rag300.py" --label "$LABEL" --bis 100 --modell "$MODELL" 2>&1 | tee -a "$LOG"; zippen ;;
  alles)  python "$EV/gpt_rag300.py" --label "$LABEL" --modell "$MODELL" 2>&1 | tee -a "$LOG"; zippen ;;
  *) echo "unbekannt: $cmd (test | prompt | pilot | q100 | alles)"; exit 1 ;;
esac

#!/usr/bin/env bash
# N100: Antworten OHNE RAG (Prompt O-v1) und MIT RAG (volle Pipeline, aktuelle Version) für alle 100 Fragen,
# gemeinsame Wissensbasis fischer_boege_v7r. Kein Richter (K-v1 ist nicht brauchbar): Bewertung durch Vorbewertung + Handprüfung.
# Start (aus ~/RAG, Umgebung pilot_rag, nur Ollama + dieses Skript laufen lassen):
#   export LERNASSISTENT_RP=RP-v5          # V11b; ohne Export gilt RP-v3
#   bash skripte/laeufe/n100_rag_vs_ohne_lauf.sh V11B 2>&1 | tee protokolle/n100_rag_vs_ohne_V11B_$(date +%Y%m%d_%H%M).txt
# Ausgabe: evaluationsdaten/vergleich_rag_RAGVGL-N100F-<LABEL>-BEIDE7.csv (70 Fischer) und ...N100B... (30 Böge) + _zusammenfassung.txt
# Dauer: Antworten grob 1,5-2 h (ohne RAG ~5-10 s/Frage, mit RAG ~40 s/Frage, Rechenfragen mit RP-v5 +10 s); danach RAGAS (viele
# Richter-Aufrufe je Frage, mehrere Stunden: Nachtlauf). Nur Antworten: OHNE_RAGAS=1 ; RAGAS-Probe: RAGAS_LIMIT=5.
# Vorher einmalig: python /pfad/patch_vergleich_logge.py  (Option --logge)
cd "$(dirname "$0")/../.." || exit 1
LABEL="${1:?Versionskennung angeben, z. B. V11B}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
KB=daten/wissensbasen/knowledge_base_fischer_boege_v7r.json
FF=daten/testfragen/testfragen_fischer_v2_chunks_beide_v7r.csv
FB=daten/testfragen/testfragen_boege_v2_v7r.csv
for f in "$KB" "$FF" "$FB"; do [ -f "$f" ] || { echo "FEHLT: $f"; exit 1; }; done
mkdir -p protokolle
echo "Rechenprüfung: ${LERNASSISTENT_RP:-RP-v3 (Standard)}"
echo "Ollama:"; ollama ps
echo "(Spalte PROCESSOR sollte 100 % GPU zeigen; sonst andere Programme schließen, sonst werden die Zeiten nicht vergleichbar.)"
RET="--retrieval hybrid_kg_rr"
echo; echo "=== Fischer (70) $(date +%H:%M) ==="
python skripte/evaluation/vergleich_mit_ohne_rag.py "RAGVGL-N100F-${LABEL}-BEIDE7" --kb "$KB" --fragen "$FF" --ideen '' $RET --judge none --logge
echo; echo "=== Böge (30) $(date +%H:%M) ==="
python skripte/evaluation/vergleich_mit_ohne_rag.py "RAGVGL-N100B-${LABEL}-BEIDE7" --kb "$KB" --fragen "$FB" --ideen '' $RET --judge none --logge
# --- RAGAS (nur MIT-RAG-Antworten; Richter mistral-nemo, nicht der Generator). Aus mit OHNE_RAGAS=1 ; Probe mit RAGAS_LIMIT=5
if [ -z "$OHNE_RAGAS" ]; then
  for m in $(ollama ps 2>/dev/null | awk 'NR>1{print $1}'); do ollama stop "$m"; done
  echo; echo "=== RAGAS $(date +%H:%M) ==="
  python skripte/evaluation/ragas_auswertung.py "RAGVGL-N100" --judge mistral-nemo --kb "$KB" ${RAGAS_LIMIT:+--limit $RAGAS_LIMIT}
  for f in ragas_ergebnisse ragas_faithfulness_details ragas_answer_relevance_details ragas_context_relevance_details; do
    [ -f "evaluationsdaten/$f.csv" ] && cp "evaluationsdaten/$f.csv" "evaluationsdaten/${f}_N100_${LABEL}.csv"
  done
fi
echo; echo "=== fertig $(date +%H:%M) ==="
ls -la evaluationsdaten/vergleich_rag_RAGVGL-N100*-"${LABEL}"-BEIDE7*

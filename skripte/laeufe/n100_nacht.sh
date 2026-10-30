#!/usr/bin/env bash
# Nachtlauf N100 (100 Fragen, gemeinsame KB v7r): MIT RAG (volle Pipeline) gegen OHNE RAG, zwei Versionen der Rechenprüfung, danach RAGAS für beide.
#   1. V11B = RP-v5 (neu)   2. V10A = RP-v3 (Vergleichslauf unter gleichen Bedingungen, gleicher Rechnerzustand)   3. RAGAS über beide
# Start (aus ~/RAG, Umgebung pilot_rag; Browser und andere GPU-Programme schließen; Windows darf nicht schlafen):
#   nohup bash skripte/laeufe/n100_nacht.sh > protokolle/n100_nacht_$(date +%Y%m%d_%H%M).txt 2>&1 &
#   tail -f protokolle/n100_nacht_*.txt         (Fortschritt ansehen; Strg+C beendet nur tail, nicht den Lauf)
# Voraussetzung: V11b installiert, patch_vergleich_logge.py ausgeführt, n100_rag_vs_ohne_lauf.sh in skripte/laeufe/.
# Dauer grob: Schritt 1 und 2 je 1,5-2 h, RAGAS mehrere Stunden. Reihenfolge so gewählt, dass die wichtigen Ergebnisse zuerst fertig sind.
cd "$(dirname "$0")/../.." || exit 1
mkdir -p protokolle
# --- Voraussetzungen prüfen (bricht ab, statt leer durchzulaufen)
fehlt=0
[ -f skripte/laeufe/n100_rag_vs_ohne_lauf.sh ] || { echo "FEHLT: skripte/laeufe/n100_rag_vs_ohne_lauf.sh (aus Downloads dorthin kopieren)"; fehlt=1; }
grep -q -- "--logge" skripte/evaluation/vergleich_mit_ohne_rag.py 2>/dev/null || { echo "FEHLT: --logge in vergleich_mit_ohne_rag.py (python patch_vergleich_logge.py ausführen)"; fehlt=1; }
grep -q "def parse_v2" lernassistent/rechenbaustein.py 2>/dev/null || { echo "FEHLT: V11b (python installiere_v11b.py ausführen)"; fehlt=1; }
for f in daten/wissensbasen/knowledge_base_fischer_boege_v7r.json daten/testfragen/testfragen_fischer_v2_chunks_beide_v7r.csv daten/testfragen/testfragen_boege_v2_v7r.csv; do
  [ -f "$f" ] || { echo "FEHLT: $f"; fehlt=1; }
done
[ "$fehlt" -eq 0 ] || { echo "Abbruch."; exit 1; }
echo "=== Start $(date) ==="; ollama ps
echo; echo "##### 1/3 V11B (RP-v5) $(date +%H:%M)"
LERNASSISTENT_RP=RP-v5 OHNE_RAGAS=1 bash skripte/laeufe/n100_rag_vs_ohne_lauf.sh V11B
echo; echo "##### 2/3 V10A (RP-v3) $(date +%H:%M)"
LERNASSISTENT_RP=RP-v3 OHNE_RAGAS=1 bash skripte/laeufe/n100_rag_vs_ohne_lauf.sh V10A
echo; echo "##### 3/3 RAGAS $(date +%H:%M)"
if ! grep -q "RAGVGL-N100" evaluationsdaten/interaktionen.csv 2>/dev/null; then echo "Keine RAGVGL-N100-Zeilen in interaktionen.csv: RAGAS übersprungen (laufen Schritte 1 und 2 mit --logge?)"; exit 1; fi
for m in $(ollama ps 2>/dev/null | awk 'NR>1{print $1}'); do ollama stop "$m"; done
KB=daten/wissensbasen/knowledge_base_fischer_boege_v7r.json
python skripte/evaluation/ragas_auswertung.py "RAGVGL-N100" --judge mistral-nemo --kb "$KB" ${RAGAS_LIMIT:+--limit $RAGAS_LIMIT}
for f in ragas_ergebnisse ragas_faithfulness_details ragas_answer_relevance_details ragas_context_relevance_details; do
  [ -f "evaluationsdaten/$f.csv" ] && cp "evaluationsdaten/$f.csv" "evaluationsdaten/${f}_N100_NACHT.csv"
done
echo; echo "=== fertig $(date) ==="
ls -la evaluationsdaten/vergleich_rag_RAGVGL-N100* evaluationsdaten/ragas_*_N100_NACHT.csv 2>/dev/null

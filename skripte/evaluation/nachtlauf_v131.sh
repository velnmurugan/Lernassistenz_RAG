#!/usr/bin/env bash
# V13.1 auf N100: Offline-Tests -> ein Lauf V131 (RP-v7 + RB-v4, Prompt G-v5) -> Vergleich mit V11B und V13B. Vordergrund, kein nohup.
# Start (aus ~/RAG, pilot_rag, nur Ollama läuft):
#   bash skripte/evaluation/nachtlauf_v131.sh 2>&1 | tee protokolle/nachtlauf_v131_$(date +%Y%m%d_%H%M).txt
# Dauer ca. 1,5 h (ohne RAGAS).
cd "$(dirname "$0")/../.." || exit 1
mkdir -p protokolle
echo "=== Offline-Tests $(date +%H:%M) ==="
for t in teste_v131_offline teste_v13_offline teste_v12_offline teste_rb2_offline teste_rb_offline teste_v10_offline; do
  timeout 300 python skripte/evaluation/$t.py > "protokolle/$t.txt" 2>&1; rc=$?
  echo "$t: $(tail -1 protokolle/$t.txt) (rc=$rc)"
  [ $rc -eq 0 ] || { echo "ABBRUCH: $t fehlgeschlagen (rc=$rc), siehe protokolle/$t.txt"; exit 1; }
done
echo; echo "=== Lauf V131: RP-v7 + RB-v4, G-v5 $(date +%H:%M) ==="
OHNE_RAGAS=1 LERNASSISTENT_RP=RP-v7 LERNASSISTENT_G=G-v5 bash skripte/laeufe/n100_rag_vs_ohne_lauf.sh V131
echo; echo "=== Vergleich $(date +%H:%M) ==="
python skripte/evaluation/vergleiche_n100_laeufe.py V11B V13B V131
python -m zipfile -c V131_ergebnisse.zip evaluationsdaten/vergleich_rag_RAGVGL-N100*-V131-BEIDE7*.* evaluationsdaten/n100_vergleich_V11B_V13B_V131.csv \
  $(ls -t protokolle/nachtlauf_v131_*.txt 2>/dev/null | head -1) && echo "Ergebnis-Zip: ~/RAG/V131_ergebnisse.zip"
echo "=== fertig $(date +%H:%M) ==="

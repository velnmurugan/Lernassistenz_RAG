#!/usr/bin/env bash
# V13.2 auf N100: Offline-Tests -> Lauf V132 (RP-v8 + RB-v4, G-v5, KB v7r) -> Vergleich mit V11B und V13B. Vordergrund, kein nohup.
# Start (aus ~/RAG, pilot_rag, nur Ollama läuft):
#   bash skripte/evaluation/nachtlauf_v132.sh 2>&1 | tee protokolle/nachtlauf_v132_$(date +%Y%m%d_%H%M).txt
# Dauer ca. 1,5 h (ohne RAGAS).
cd "$(dirname "$0")/../.." || exit 1
mkdir -p protokolle
echo "=== Offline-Tests $(date +%H:%M) ==="
for t in teste_v132_offline teste_v131_offline teste_v13_offline teste_v12_offline teste_rb2_offline teste_rb_offline teste_v10_offline; do
  timeout 300 python skripte/evaluation/$t.py > "protokolle/$t.txt" 2>&1; rc=$?
  echo "$t: $(tail -1 protokolle/$t.txt) (rc=$rc)"
  [ $rc -eq 0 ] || { echo "ABBRUCH: $t fehlgeschlagen (rc=$rc), siehe protokolle/$t.txt"; exit 1; }
done
echo; echo "=== Lauf V132: RP-v8 + RB-v4, G-v5 $(date +%H:%M) ==="
OHNE_RAGAS=1 LERNASSISTENT_RP=RP-v8 LERNASSISTENT_G=G-v5 bash skripte/laeufe/n100_rag_vs_ohne_lauf.sh V132
echo; echo "=== Vergleich $(date +%H:%M) ==="
python skripte/evaluation/vergleiche_n100_laeufe.py V11B V13B V132
python -m zipfile -c V132_ergebnisse.zip evaluationsdaten/vergleich_rag_RAGVGL-N100*-V132-BEIDE7*.* evaluationsdaten/n100_vergleich_V11B_V13B_V132.csv \
  $(ls -t protokolle/nachtlauf_v132_*.txt 2>/dev/null | head -1) && cp V132_ergebnisse.zip "/mnt/c/Users/Vel Narayanasamy/Downloads/" 2>/dev/null
echo "Ergebnis-Zip: ~/RAG/V132_ergebnisse.zip (auch in Windows-Downloads)"
echo "=== fertig $(date +%H:%M) ==="

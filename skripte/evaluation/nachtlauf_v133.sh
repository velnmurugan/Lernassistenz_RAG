#!/usr/bin/env bash
# V13.3 auf N100: Offline-Tests -> Lauf V133 (RP-v9, FS-v3, G-v5, Kontext 8192) -> Vergleich mit V11B und V13B. Vordergrund, kein nohup.
# Start (aus ~/RAG, pilot_rag, nur Ollama läuft):
#   bash skripte/evaluation/nachtlauf_v133.sh 2>&1 | tee protokolle/nachtlauf_v133_$(date +%Y%m%d_%H%M).txt
# Dauer ca. 1,5-2 h (Denkmodus nur bei markierten Rechenfragen, je ~4 min).
cd "$(dirname "$0")/../.." || exit 1
mkdir -p protokolle
echo "=== Offline-Tests $(date +%H:%M) ==="
for t in teste_v133_offline teste_v132_offline teste_v131_offline teste_v13_offline teste_v12_offline teste_rb2_offline teste_rb_offline teste_v10_offline; do
  timeout 300 python skripte/evaluation/$t.py > "protokolle/$t.txt" 2>&1; rc=$?
  echo "$t: $(tail -1 protokolle/$t.txt) (rc=$rc)"
  [ $rc -eq 0 ] || { echo "ABBRUCH: $t fehlgeschlagen (rc=$rc), siehe protokolle/$t.txt"; exit 1; }
done
echo; echo "=== Lauf V133: RP-v9, FS-v3, G-v5, CTX 8192 $(date +%H:%M) ==="
OHNE_RAGAS=1 LERNASSISTENT_RP=RP-v9 LERNASSISTENT_G=G-v5 LERNASSISTENT_FS=FS-v3 LERNASSISTENT_CTX=8192 bash skripte/laeufe/n100_rag_vs_ohne_lauf.sh V133
echo; echo "=== Vergleich $(date +%H:%M) ==="
python skripte/evaluation/vergleiche_n100_laeufe.py V11B V13B V133
python -m zipfile -c V133_ergebnisse.zip evaluationsdaten/vergleich_rag_RAGVGL-N100*-V133-BEIDE7*.* evaluationsdaten/n100_vergleich_V11B_V13B_V133.csv \
  $(ls -t protokolle/nachtlauf_v133_*.txt 2>/dev/null | head -1) && cp V133_ergebnisse.zip "$(bash "$HOME/RAG/skripte/werkzeuge/windows_downloads.sh")/" 2>/dev/null
echo "Ergebnis-Zip: ~/RAG/V133_ergebnisse.zip (auch in Windows-Downloads)"
echo "=== fertig $(date +%H:%M) ==="

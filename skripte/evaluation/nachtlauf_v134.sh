#!/usr/bin/env bash
# V13.4 Nachtlauf: Offline-Tests -> Diagnose Buchergebnisse -> Rechenvarianten RV-v1 (22) -> N100 -> Vergleich. Vordergrund, kein nohup.
# Start (aus ~/RAG, pilot_rag, nur Ollama läuft):
#   bash skripte/evaluation/nachtlauf_v134.sh 2>&1 | tee protokolle/nachtlauf_v134_$(date +%Y%m%d_%H%M).txt
# Dauer ca. 3,5-4 h (RV ~1,5 h, N100 ~2 h).
cd "$(dirname "$0")/../.." || exit 1
mkdir -p protokolle
export PYTHONUNBUFFERED=1
echo "=== Offline-Tests $(date +%H:%M) ==="
for t in teste_v134_offline teste_v133_offline teste_v132_offline teste_v131_offline teste_v13_offline teste_v12_offline teste_rb2_offline teste_rb_offline teste_v10_offline; do
  timeout 300 python skripte/evaluation/$t.py > "protokolle/$t.txt" 2>&1; rc=$?
  echo "$t: $(tail -1 protokolle/$t.txt) (rc=$rc)"
  [ $rc -eq 0 ] || { echo "ABBRUCH: $t fehlgeschlagen (rc=$rc), siehe protokolle/$t.txt"; exit 1; }
done
echo; echo "=== Diagnose Buchergebnisse $(date +%H:%M) ==="
python skripte/evaluation/diagnose_buchergebnisse.py | tee protokolle/diagnose_buchergebnisse.txt
export LERNASSISTENT_RP=RP-v10 LERNASSISTENT_G=G-v5 LERNASSISTENT_FS=FS-v3 LERNASSISTENT_CTX=8192
echo; echo "=== Rechenvarianten V134 $(date +%H:%M) ==="
rm -f evaluationsdaten/rechen_varianten_V134.csv
python skripte/evaluation/teste_rechen_varianten.py V134 2>&1 | tee protokolle/rechen_varianten_V134.txt
echo; echo "=== N100 V134: RP-v10, FS-v3, G-v5, CTX 8192 $(date +%H:%M) ==="
OHNE_RAGAS=1 bash skripte/laeufe/n100_rag_vs_ohne_lauf.sh V134
echo; echo "=== Vergleich $(date +%H:%M) ==="
python skripte/evaluation/vergleiche_n100_laeufe.py V11B V13B V134
python -m zipfile -c V134_ergebnisse.zip evaluationsdaten/vergleich_rag_RAGVGL-N100*-V134-BEIDE7*.* evaluationsdaten/n100_vergleich_V11B_V13B_V134.csv \
  evaluationsdaten/rechen_varianten_V134.csv protokolle/rechen_varianten_V134.txt protokolle/diagnose_buchergebnisse.txt \
  $(ls -t protokolle/nachtlauf_v134_*.txt 2>/dev/null | head -1) && cp V134_ergebnisse.zip "/mnt/c/Users/Vel Narayanasamy/Downloads/" 2>/dev/null
echo "Ergebnis-Zip: ~/RAG/V134_ergebnisse.zip (auch in Windows-Downloads)"
echo "=== fertig $(date +%H:%M) ==="

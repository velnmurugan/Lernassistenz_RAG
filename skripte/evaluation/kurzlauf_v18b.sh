#!/usr/bin/env bash
# V18b Kurzlauf (nur RAG). Vordergrund, kein nohup. LERNASSISTENT_V18=ADE (B aus).
# A-Fälle: RV-v1 R01, R17; RV-v2 R17, R20; N100 F61.  Kontrollen (bisher richtig): RV-v1 R09, R13; RV-v2 R04, R10; N100 F4, F7, F15, F62.
# Vergleich: V18-Kurzlauf (A-Fälle) und V16/V17 (Kontrollen).
# Start (aus ~/RAG, pilot_rag, nur Ollama läuft):
#   bash skripte/evaluation/kurzlauf_v18.sh 2>&1 | tee protokolle/kurzlauf_v18b_$(date +%Y%m%d_%H%M).txt
cd "$(dirname "$0")/../.." || exit 1
mkdir -p protokolle
export PYTHONUNBUFFERED=1 LERNASSISTENT_G=G-v5 LERNASSISTENT_CTX=8192 LERNASSISTENT_RW=
echo "=== Offline-Tests $(date +%H:%M) ==="
for m in aus ADE; do
  LERNASSISTENT_V18=$( [ $m = aus ] && echo "" || echo $m ) timeout 300 python skripte/evaluation/teste_v18_offline.py $m > "protokolle/teste_v18_offline_$m.txt" 2>&1; rc=$?
  echo "teste_v18_offline $m: $(tail -1 protokolle/teste_v18_offline_$m.txt) (rc=$rc)"
  [ $rc -eq 0 ] || { echo "ABBRUCH: teste_v18_offline $m fehlgeschlagen"; exit 1; }
done
for t in teste_v17_offline teste_v16_offline teste_v15_offline teste_v14_offline; do
  LERNASSISTENT_V18=ADE timeout 300 python skripte/evaluation/$t.py > "protokolle/$t.txt" 2>&1; rc=$?
  echo "$t: $(tail -1 protokolle/$t.txt) (rc=$rc)"
  [ $rc -eq 0 ] || { echo "ABBRUCH: $t fehlgeschlagen (rc=$rc), siehe protokolle/$t.txt"; exit 1; }
done
export LERNASSISTENT_RP=RP-v13 LERNASSISTENT_RB=RB-v8 LERNASSISTENT_FS=FS-v3 LERNASSISTENT_V18=ADE
lauf () {  # $1 Label  $2 Fragen-CSV  $3 Fragen
  echo; echo "=== $1 (RP=$LERNASSISTENT_RP RB=$LERNASSISTENT_RB V18=$LERNASSISTENT_V18) $(date +%H:%M) ==="
  rm -f "evaluationsdaten/rechen_varianten_$1.csv"
  python skripte/evaluation/teste_rechen_varianten.py "$1" --fragen "$2" --nur "$3" 2>&1 | tee "protokolle/rechen_varianten_$1.txt"
}
lauf RV1-V18b daten/testfragen/rechen_varianten_v1.csv R01,R17,R09,R13
lauf RV2-V18b daten/testfragen/rechen_varianten_v2.csv R17,R20,R04,R10
lauf N100R-V18b daten/testfragen/n100_rechnung_v1.csv F61,F4,F7,F15,F62
dateien=""
for x in evaluationsdaten/rechen_varianten_RV1-V18b.csv evaluationsdaten/rechen_varianten_RV2-V18b.csv evaluationsdaten/rechen_varianten_N100R-V18b.csv \
         protokolle/rechen_varianten_RV1-V18b.txt protokolle/rechen_varianten_RV2-V18b.txt protokolle/rechen_varianten_N100R-V18b.txt \
         $(ls -t protokolle/kurzlauf_v18b_*.txt 2>/dev/null | head -1); do
  [ -f "$x" ] && dateien="$dateien $x"
done
python -m zipfile -c V18b_ergebnisse.zip $dateien && cp V18b_ergebnisse.zip "/mnt/c/Users/Vel Narayanasamy/Downloads/" 2>/dev/null
echo "Ergebnis-Zip: ~/RAG/V18b_ergebnisse.zip (auch in Windows-Downloads)"
echo "=== fertig $(date +%H:%M) ==="

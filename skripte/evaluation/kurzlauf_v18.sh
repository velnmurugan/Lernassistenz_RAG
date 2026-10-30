#!/usr/bin/env bash
# V18 Kurzlauf (nur RAG, 5 Fragen der Kategorie A). Vordergrund, kein nohup.
# A-Fälle (richtige Nachrechnung nicht genutzt): RV-v1 R01, R17; RV-v2 R17, R20; N100 F61.
# Vergleich: dieselben Fragen in V16/V17 (R01/R17 RV-v1 und R20 RV-v2 aus dem V16-Nachtlauf).
# Start (aus ~/RAG, pilot_rag, nur Ollama läuft):
#   bash skripte/evaluation/kurzlauf_v18.sh 2>&1 | tee protokolle/kurzlauf_v18_$(date +%Y%m%d_%H%M).txt
cd "$(dirname "$0")/../.." || exit 1
mkdir -p protokolle
export PYTHONUNBUFFERED=1 LERNASSISTENT_G=G-v5 LERNASSISTENT_CTX=8192 LERNASSISTENT_RW=
echo "=== Offline-Tests $(date +%H:%M) ==="
for m in aus AB; do
  LERNASSISTENT_V18=$( [ $m = aus ] && echo "" || echo $m ) timeout 300 python skripte/evaluation/teste_v18_offline.py $m > "protokolle/teste_v18_offline_$m.txt" 2>&1; rc=$?
  echo "teste_v18_offline $m: $(tail -1 protokolle/teste_v18_offline_$m.txt) (rc=$rc)"
  [ $rc -eq 0 ] || { echo "ABBRUCH: teste_v18_offline $m fehlgeschlagen"; exit 1; }
done
for t in teste_v17_offline teste_v16_offline teste_v15_offline; do
  timeout 300 python skripte/evaluation/$t.py > "protokolle/$t.txt" 2>&1; rc=$?
  echo "$t: $(tail -1 protokolle/$t.txt) (rc=$rc)"
  [ $rc -eq 0 ] || { echo "ABBRUCH: $t fehlgeschlagen (rc=$rc), siehe protokolle/$t.txt"; exit 1; }
done
export LERNASSISTENT_RP=RP-v13 LERNASSISTENT_RB=RB-v8 LERNASSISTENT_FS=FS-v3 LERNASSISTENT_V18=AB
lauf () {  # $1 Label  $2 Fragen-CSV  $3 Fragen
  echo; echo "=== $1 (RP=$LERNASSISTENT_RP RB=$LERNASSISTENT_RB V18=$LERNASSISTENT_V18) $(date +%H:%M) ==="
  rm -f "evaluationsdaten/rechen_varianten_$1.csv"
  python skripte/evaluation/teste_rechen_varianten.py "$1" --fragen "$2" --nur "$3" 2>&1 | tee "protokolle/rechen_varianten_$1.txt"
}
lauf RV1-V18 daten/testfragen/rechen_varianten_v1.csv R01,R17
lauf RV2-V18 daten/testfragen/rechen_varianten_v2.csv R17,R20
lauf N100R-V18 daten/testfragen/n100_rechnung_v1.csv F61
dateien=""
for x in evaluationsdaten/rechen_varianten_RV1-V18.csv evaluationsdaten/rechen_varianten_RV2-V18.csv evaluationsdaten/rechen_varianten_N100R-V18.csv \
         protokolle/rechen_varianten_RV1-V18.txt protokolle/rechen_varianten_RV2-V18.txt protokolle/rechen_varianten_N100R-V18.txt \
         $(ls -t protokolle/kurzlauf_v18_*.txt 2>/dev/null | head -1); do
  [ -f "$x" ] && dateien="$dateien $x"
done
python -m zipfile -c V18_ergebnisse.zip $dateien && cp V18_ergebnisse.zip "$(bash "$HOME/RAG/skripte/werkzeuge/windows_downloads.sh")/" 2>/dev/null
echo "Ergebnis-Zip: ~/RAG/V18_ergebnisse.zip (auch in Windows-Downloads)"
echo "=== fertig $(date +%H:%M) ==="

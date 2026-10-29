#!/usr/bin/env bash
# V19 Kurzlauf (nur RAG). Vordergrund, kein nohup. Aufruf: kurzlauf_v19a.sh [A|AB|aus]   (Standard A; der Modus kommt NUR aus dem Argument, nicht aus der Umgebung)
# Zielfälle (Formel fehlte im Kontext oder wurde knapp verdrängt): RV-v1 R07, R12; RV-v2 R07, R12, R13.
# Kontrollen (Formel war schon im Kontext, Antworten dürfen nicht schlechter werden): RV-v2 R04, R10, R11, R14, R17, R18, R22; N100 F15, F61, F62.
# Start (aus ~/RAG, pilot_rag, nur Ollama läuft):
#   bash skripte/evaluation/kurzlauf_v19a.sh 2>&1 | tee protokolle/kurzlauf_v19a_$(date +%Y%m%d_%H%M).txt
cd "$(dirname "$0")/../.." || exit 1
mkdir -p protokolle
MODUS=${1:-A}; [ "$MODUS" = "aus" ] && V19="" || V19="$MODUS"   # A | AB | aus (AB = Formelsuche vorab + Parser-Korrekturen V19b)
ETI=$([ "$MODUS" = "aus" ] && echo "V19aaus" || echo "V19${MODUS,,}")
export PYTHONUNBUFFERED=1 LERNASSISTENT_G=G-v5 LERNASSISTENT_CTX=8192 LERNASSISTENT_RW=
echo "=== Offline-Tests $(date +%H:%M) ==="
for m in "" A; do
  LERNASSISTENT_V19=$m timeout 300 python skripte/evaluation/teste_v19_offline.py > "protokolle/teste_v19_offline_${m:-aus}.txt" 2>&1; rc=$?
  echo "teste_v19_offline ${m:-aus}: $(tail -1 protokolle/teste_v19_offline_${m:-aus}.txt) (rc=$rc)"
  [ $rc -eq 0 ] || { echo "ABBRUCH: teste_v19_offline ${m:-aus} fehlgeschlagen"; exit 1; }
done
for t in teste_v18_offline teste_v17_offline teste_v16_offline teste_v15_offline teste_v14_offline; do
  arg=""; [ $t = teste_v18_offline ] && arg=ADEK
  LERNASSISTENT_V18=ADEK LERNASSISTENT_V19=A timeout 300 python skripte/evaluation/$t.py $arg > "protokolle/$t.txt" 2>&1; rc=$?
  echo "$t: $(tail -1 protokolle/$t.txt) (rc=$rc)"
  [ $rc -eq 0 ] || { echo "ABBRUCH: $t fehlgeschlagen (rc=$rc), siehe protokolle/$t.txt"; exit 1; }
done
export LERNASSISTENT_RP=RP-v13 LERNASSISTENT_RB=RB-v8 LERNASSISTENT_FS=FS-v3 LERNASSISTENT_V18=ADEK LERNASSISTENT_V19=$V19
lauf () {  # $1 Label  $2 Fragen-CSV  $3 Fragen
  echo; echo "=== $1 (RP=$LERNASSISTENT_RP RB=$LERNASSISTENT_RB V18=$LERNASSISTENT_V18 V19=${LERNASSISTENT_V19:-aus}) $(date +%H:%M) ==="
  rm -f "evaluationsdaten/rechen_varianten_$1.csv"
  python skripte/evaluation/teste_rechen_varianten.py "$1" --fragen "$2" --nur "$3" 2>&1 | tee "protokolle/rechen_varianten_$1.txt"
}
lauf RV1-$ETI daten/testfragen/rechen_varianten_v1.csv R07,R12
lauf RV2-$ETI daten/testfragen/rechen_varianten_v2.csv R07,R12,R13,R04,R10,R11,R14,R17,R18,R22
lauf N100R-$ETI daten/testfragen/n100_rechnung_v1.csv F15,F61,F62
dateien=""
for x in evaluationsdaten/rechen_varianten_RV1-$ETI.csv evaluationsdaten/rechen_varianten_RV2-$ETI.csv evaluationsdaten/rechen_varianten_N100R-$ETI.csv \
         protokolle/rechen_varianten_RV1-$ETI.txt protokolle/rechen_varianten_RV2-$ETI.txt protokolle/rechen_varianten_N100R-$ETI.txt \
         $(ls -t protokolle/kurzlauf_v19a_*.txt 2>/dev/null | head -1); do
  [ -f "$x" ] && dateien="$dateien $x"
done
python -m zipfile -c ${ETI}_ergebnisse.zip $dateien && cp ${ETI}_ergebnisse.zip "/mnt/c/Users/Vel Narayanasamy/Downloads/" 2>/dev/null
echo "Ergebnis-Zip: ~/RAG/${ETI}_ergebnisse.zip (auch in Windows-Downloads)"
echo "=== fertig $(date +%H:%M) ==="

#!/usr/bin/env bash
# V14 Nachtlauf, nur Rechenfragen: Offline-Tests -> je zwei Arme (V135 = RP-v11 ohne Werkzeug, V14 = RP-v11 + Rechenweg mit Python, RW-v5)
# auf RV-v1 (22 geänderte Buchaufgaben) und auf den 22 N100-Rechenfragen. Jeder Arm ist ein ganzer Durchgang (Determinismus-Regel).
# Vordergrund, kein nohup. Start (aus ~/RAG, pilot_rag, nur Ollama läuft):
#   bash skripte/evaluation/nachtlauf_v14.sh 2>&1 | tee protokolle/nachtlauf_v14_$(date +%Y%m%d_%H%M).txt
# Dauer ca. 4-5 h. Rechenweg-Variante: RW_NACHT (Standard RW-v5).
cd "$(dirname "$0")/../.." || exit 1
mkdir -p protokolle
export PYTHONUNBUFFERED=1
echo "=== Offline-Tests $(date +%H:%M) ==="
for t in teste_v14_offline teste_v135_offline teste_v134_offline teste_v133_offline teste_v132_offline teste_v131_offline teste_v13_offline teste_v12_offline teste_rb2_offline teste_rb_offline teste_v10_offline; do
  timeout 300 python skripte/evaluation/$t.py > "protokolle/$t.txt" 2>&1; rc=$?
  echo "$t: $(tail -1 protokolle/$t.txt) (rc=$rc)"
  [ $rc -eq 0 ] || { echo "ABBRUCH: $t fehlgeschlagen (rc=$rc), siehe protokolle/$t.txt"; exit 1; }
done
export LERNASSISTENT_RP=RP-v11 LERNASSISTENT_G=G-v5 LERNASSISTENT_FS=FS-v3 LERNASSISTENT_CTX=8192
lauf () {  # $1 Label, $2 RW-Version oder leer, $3 Fragen-CSV
  echo; echo "=== $1 (RW=${2:--}) $(date +%H:%M) ==="
  rm -f "evaluationsdaten/rechen_varianten_$1.csv"
  LERNASSISTENT_RW="$2" python skripte/evaluation/teste_rechen_varianten.py "$1" --fragen "$3" 2>&1 | tee "protokolle/rechen_varianten_$1.txt"
}
lauf V135 ""    daten/testfragen/rechen_varianten_v1.csv
lauf V14  "${RW_NACHT:-RW-v5}" daten/testfragen/rechen_varianten_v1.csv
lauf N100R-V135 ""    daten/testfragen/n100_rechnung_v1.csv
lauf N100R-V14  "${RW_NACHT:-RW-v5}" daten/testfragen/n100_rechnung_v1.csv
echo; echo "=== Zusammenfassung $(date +%H:%M) ==="
for l in V135 V14 N100R-V135 N100R-V14; do echo "$l: $(tail -1 protokolle/rechen_varianten_$l.txt)"; done
python -m zipfile -c V14_ergebnisse.zip evaluationsdaten/rechen_varianten_{V135,V14,N100R-V135,N100R-V14}.csv \
  protokolle/rechen_varianten_{V135,V14,N100R-V135,N100R-V14}.txt $(ls -t protokolle/nachtlauf_v14_*.txt 2>/dev/null | head -1) \
  && cp V14_ergebnisse.zip "/mnt/c/Users/Vel Narayanasamy/Downloads/" 2>/dev/null
echo "Ergebnis-Zip: ~/RAG/V14_ergebnisse.zip (auch in Windows-Downloads)"
echo "=== fertig $(date +%H:%M) ==="

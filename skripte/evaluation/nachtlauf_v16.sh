#!/usr/bin/env bash
# V16 Nachtlauf (ca. 6–7 h, nur RAG, kein Vergleichslauf ohne RAG). Vordergrund, kein nohup.
# Arme (jeweils ein vollständiger Durchlauf):
#   A  V16      = RP-v12 + RB-v7 (Einheiten umrechnen, Bestätigung mit Retry, Kopfsatz + weiteres Ergebnis, Antwort ohne Ergebnis)
#               auf RV-v1 (22), N100-Rechnen (22), RV-v2 (21, NEU: dieselben Aufgaben mit neuen Zahlen, nie zur Entwicklung genutzt)
#   B  V135     = RP-v11 + RB-v6 (Basis) auf RV-v2   -> verallgemeinern die V15/V16-Änderungen auf neue Zahlen?
#   C  OHNE     = keine Rechenprüfung, keine Formelsuche (nur Modell + Retrieval) auf RV-v1, N100-Rechnen, RV-v2
#               -> wie viel bringt die Python-Prüfung insgesamt?
#   D  N100 voll (100 Fragen) mit V16, nur RAG -> Rückschritte bei Nicht-Rechenfragen?
# Start (aus ~/RAG, pilot_rag, nur Ollama läuft):
#   bash skripte/evaluation/nachtlauf_v16.sh 2>&1 | tee protokolle/nachtlauf_v16_$(date +%Y%m%d_%H%M).txt
cd "$(dirname "$0")/../.." || exit 1
mkdir -p protokolle
export PYTHONUNBUFFERED=1 LERNASSISTENT_G=G-v5 LERNASSISTENT_CTX=8192 LERNASSISTENT_RW=
echo "=== Offline-Tests $(date +%H:%M) ==="
for t in teste_v16_offline teste_v15_offline teste_v14_offline teste_v135_offline teste_v134_offline teste_v133_offline teste_v132_offline teste_v131_offline teste_v13_offline; do
  timeout 300 python skripte/evaluation/$t.py > "protokolle/$t.txt" 2>&1; rc=$?
  echo "$t: $(tail -1 protokolle/$t.txt) (rc=$rc)"
  [ $rc -eq 0 ] || { echo "ABBRUCH: $t fehlgeschlagen (rc=$rc), siehe protokolle/$t.txt"; exit 1; }
done
lauf () {  # $1 Label  $2 Fragen-CSV
  echo; echo "=== $1 (RP=${LERNASSISTENT_RP:--} RB=${LERNASSISTENT_RB:--} FS=$LERNASSISTENT_FS) $(date +%H:%M) ==="
  rm -f "evaluationsdaten/rechen_varianten_$1.csv"
  python skripte/evaluation/teste_rechen_varianten.py "$1" --fragen "$2" 2>&1 | tee "protokolle/rechen_varianten_$1.txt"
}
RV1=daten/testfragen/rechen_varianten_v1.csv; N1R=daten/testfragen/n100_rechnung_v1.csv; RV2=daten/testfragen/rechen_varianten_v2.csv
# A
export LERNASSISTENT_RP=RP-v12 LERNASSISTENT_RB=RB-v7 LERNASSISTENT_FS=FS-v3
lauf V16 $RV1; lauf N100R-V16 $N1R; lauf RV2-V16 $RV2
# B
export LERNASSISTENT_RP=RP-v11 LERNASSISTENT_RB= LERNASSISTENT_FS=FS-v3
lauf RV2-V135 $RV2
# C
export LERNASSISTENT_RP= LERNASSISTENT_RB= LERNASSISTENT_FS=aus
lauf V16-OHNE $RV1; lauf N100R-V16-OHNE $N1R; lauf RV2-V16-OHNE $RV2
# Zwischenstand sichern, bevor der lange N100-Lauf beginnt
python skripte/evaluation/vergleiche_rechenlaeufe.py V135 V15 V16 V16-OHNE 2>&1 | tee protokolle/vergleich_rechenlaeufe.txt
# D
export LERNASSISTENT_RP=RP-v12 LERNASSISTENT_RB=RB-v7 LERNASSISTENT_FS=FS-v3
echo; echo "=== N100 voll, V16, nur RAG $(date +%H:%M) ==="
rm -f evaluationsdaten/n100_rag_V16.csv
python skripte/evaluation/lauf_n100_rag.py V16 2>&1 | tee protokolle/n100_rag_V16.txt
echo; echo "=== Vergleich $(date +%H:%M) ==="
python skripte/evaluation/vergleiche_rechenlaeufe.py V135 V15 V16 V16-OHNE 2>&1 | tee protokolle/vergleich_rechenlaeufe.txt
dateien=""
for x in evaluationsdaten/rechen_varianten_*V16*.csv evaluationsdaten/rechen_varianten_RV2-V135.csv evaluationsdaten/rechen_varianten_V135.csv \
         evaluationsdaten/rechen_varianten_N100R-V135.csv evaluationsdaten/rechen_varianten_V15.csv evaluationsdaten/rechen_varianten_N100R-V15.csv \
         evaluationsdaten/n100_rag_V16.csv evaluationsdaten/vergleich_rechenlaeufe.csv protokolle/rechen_varianten_*V16*.txt \
         protokolle/rechen_varianten_RV2-V135.txt protokolle/n100_rag_V16.txt protokolle/vergleich_rechenlaeufe.txt \
         $(ls -t protokolle/nachtlauf_v16_*.txt 2>/dev/null | head -1); do
  [ -f "$x" ] && dateien="$dateien $x"
done
python -m zipfile -c V16_ergebnisse.zip $dateien && cp V16_ergebnisse.zip "$(bash "$HOME/RAG/skripte/werkzeuge/windows_downloads.sh")/" 2>/dev/null
echo "Ergebnis-Zip: ~/RAG/V16_ergebnisse.zip (auch in Windows-Downloads)"
echo "=== fertig $(date +%H:%M) ==="

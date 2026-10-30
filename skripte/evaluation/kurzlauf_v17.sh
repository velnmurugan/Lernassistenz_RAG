#!/usr/bin/env bash
# V17b Kurzlauf (ca. 50 min, nur RAG). Vordergrund, kein nohup. RB-v8 = Dimensionsprüfung + Lesekorrekturen, RP-v13 = strenger Vergleich.
# Nur die Fragen, die V17b betrifft, plus Kontrollen:
#   RV-v2: R02 R03 R09 R11 R16 (abweichung_ungestuetzt), R17 (kopf_korrigiert falsch), R06 (falsch, Prüfung ok), R04 R10 (Kontrolle richtig)
#   N100-Rechnen: F1 (falsche Bestätigung), B24 F61 (abweichung_ungestuetzt), F37 (ungeprüft), F4 F7 F15 F62 (Kontrolle richtig)
#   RV-v1: R09 (Nachrechnung ohne Länge, dimensionsfalsch), R13 (Kontrolle: Einheit in RECHNUNG, richtig)
# Vergleich: dieselben Fragen im V16-Nachtlauf. Hinweis: RV-v2 ist ab V17 Entwicklungsdaten (nicht mehr unberührt).
# Start (aus ~/RAG, pilot_rag, nur Ollama läuft):
#   bash skripte/evaluation/kurzlauf_v17.sh 2>&1 | tee protokolle/kurzlauf_v17_$(date +%Y%m%d_%H%M).txt
cd "$(dirname "$0")/../.." || exit 1
mkdir -p protokolle
export PYTHONUNBUFFERED=1 LERNASSISTENT_G=G-v5 LERNASSISTENT_CTX=8192 LERNASSISTENT_RW=
echo "=== Offline-Tests $(date +%H:%M) ==="
for t in teste_v17_offline teste_v16_offline teste_v15_offline teste_v14_offline teste_v135_offline teste_v134_offline; do
  timeout 300 python skripte/evaluation/$t.py > "protokolle/$t.txt" 2>&1; rc=$?
  echo "$t: $(tail -1 protokolle/$t.txt) (rc=$rc)"
  [ $rc -eq 0 ] || { echo "ABBRUCH: $t fehlgeschlagen (rc=$rc), siehe protokolle/$t.txt"; exit 1; }
done
export LERNASSISTENT_RP=RP-v13 LERNASSISTENT_RB=RB-v8 LERNASSISTENT_FS=FS-v3
lauf () {  # $1 Label  $2 Fragen-CSV  $3 Fragen
  echo; echo "=== $1 (RP=$LERNASSISTENT_RP RB=$LERNASSISTENT_RB) $(date +%H:%M) ==="
  rm -f "evaluationsdaten/rechen_varianten_$1.csv"
  python skripte/evaluation/teste_rechen_varianten.py "$1" --fragen "$2" --nur "$3" 2>&1 | tee "protokolle/rechen_varianten_$1.txt"
}
lauf RV2-V17 daten/testfragen/rechen_varianten_v2.csv R02,R03,R09,R11,R16,R17,R06,R04,R10
lauf N100R-V17 daten/testfragen/n100_rechnung_v1.csv F1,B24,F61,F37,F4,F7,F15,F62
lauf RV1-V17 daten/testfragen/rechen_varianten_v1.csv R09,R13
dateien=""
for x in evaluationsdaten/rechen_varianten_RV2-V17.csv evaluationsdaten/rechen_varianten_N100R-V17.csv evaluationsdaten/rechen_varianten_RV1-V17.csv \
         protokolle/rechen_varianten_RV2-V17.txt protokolle/rechen_varianten_N100R-V17.txt protokolle/rechen_varianten_RV1-V17.txt \
         $(ls -t protokolle/kurzlauf_v17_*.txt 2>/dev/null | head -1); do
  [ -f "$x" ] && dateien="$dateien $x"
done
python -m zipfile -c V17_ergebnisse.zip $dateien && cp V17_ergebnisse.zip "$(bash "$HOME/RAG/skripte/werkzeuge/windows_downloads.sh")/" 2>/dev/null
echo "Ergebnis-Zip: ~/RAG/V17_ergebnisse.zip (auch in Windows-Downloads)"
echo "=== fertig $(date +%H:%M) ==="

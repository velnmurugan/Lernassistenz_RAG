#!/usr/bin/env bash
# V12.9 Nachtlauf (ca. 5-6 h, Vordergrund, alles in evaluationsdaten/V12_9_nachtlauf.log). Start aus ~/RAG, Ollama läuft:
#   bash skripte/evaluation/nachtlauf_v12_9.sh
# Rechner vorher wachhalten (Windows: Energieoptionen "Energie sparen: nie"), sonst bricht die Zeitmessung ein (V11B Böge, 21 Okt).
# Schritte unabhängig: ein Fehler stoppt den Lauf nicht. Optional: SCHRITTE="1 2 3" bash ... (Standard: 1 2 3 4 5).
set -u
SCHRITTE="${SCHRITTE:-1 2 3 4 5}"
mkdir -p evaluationsdaten
log=evaluationsdaten/V12_9_nachtlauf.log
zeit() { echo; echo "### $1 – $(date '+%d.%m. %H:%M')"; }
{
echo "V12.9 Nachtlauf Start $(date)"; (ollama list 2>/dev/null | head -8) || true
for s in $SCHRITTE; do case $s in
1) zeit "1/5 Offline-Tests (ca. 2 min)"
   for t in teste_v12_offline teste_rb2_offline teste_rb_offline teste_v10_offline; do python skripte/evaluation/$t.py | tail -1; done ;;
2) zeit "2/5 Bildabgleich gegen Abbildungen der Wissensbasis (ca. 5-15 min; Bilder in testbilder/ und testbilder/abbildungen/)"
   if [ -d testbilder ]; then python skripte/evaluation/teste_bildabgleich.py BA-V12-9; else echo "übersprungen: Ordner testbilder fehlt"; fi ;;
3) zeit "3/5 Bildfragen, 9 Varianten in getrennten Durchgängen (ca. 1-1,5 h)"
   if [ -d testbilder ]; then python skripte/evaluation/teste_bildfragen.py BF-V12-9; else echo "übersprungen: Ordner testbilder fehlt"; fi ;;
4) zeit "4/5 A/B Formelsuche aus gegen FS-v2, N100-Rechenfragen + 3 Varianten (ca. 1,5 h)"
   python skripte/evaluation/vergleiche_v11b_v12.py V12-9-AB ;;
5) zeit "5/5 N100 komplette Regression beider Bücher mit V12.9 (ca. 2-3 h; nur wenn das Skript existiert)"
   if [ -f skripte/laeufe/n100_beide_lauf.sh ]; then bash skripte/laeufe/n100_beide_lauf.sh V12-9; else echo "übersprungen: skripte/laeufe/n100_beide_lauf.sh nicht gefunden (Aufruf wie beim V11B-Lauf)"; fi ;;
esac; done
echo; echo "FERTIG $(date)"
} 2>&1 | tee "$log"

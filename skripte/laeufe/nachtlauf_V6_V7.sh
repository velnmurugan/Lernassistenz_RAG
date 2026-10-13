#!/usr/bin/env bash
# Nachtlauf: V6 (fester Prompt-Satz) auf Böge + Fischer, V7 (MinerU + Struktur-Chunks, ohne/mit VLM-
# Bildbeschreibungen) auf Fischer, danach RAGAS für alles und V4 mit den neuen Richter-Prompts.
# Voraussetzung: python skripte/setup/pruefe_umgebung.py meldet ALLES OK.
# Start (im Projektordner, Umgebung pilot_rag aktiv):
#   bash skripte/laeufe/nachtlauf_V6_V7.sh 2>&1 | tee protokolle/nachtlauf_$(date +%Y%m%d).txt
# Dauer grob 6–9 h. Schritte laufen weiter, auch wenn einer fehlschlägt; am Ende steht eine Übersicht.
cd "$(dirname "$0")/../.." || exit 1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
RET="--retrieval hybrid_kg_rr --rrf-k 5"
FISCHER_PDF=$(ls daten/quellen/fischer/*.pdf | head -1)
KB_F6=daten/wissensbasen/knowledge_base_fischer.json
KB_F7A=daten/wissensbasen/knowledge_base_fischer_v7a.json
KB_F7B=daten/wissensbasen/knowledge_base_fischer_v7b.json
FRAGEN_F=daten/testfragen/testfragen_fischer_v1.csv
STATUS=()

schritt() { echo; echo "=================== $(date +%H:%M) $1 ==================="; }
merke() { if [ "$2" -eq 0 ]; then STATUS+=("OK     $1"); else STATUS+=("FEHLER $1"); fi; }
modelle_entladen() { for m in $(ollama ps 2>/dev/null | awk 'NR>1{print $1}'); do ollama stop "$m"; done; }

schritt "1 Fischer-Wissensbasis wie bisher (pypdf) für V6"
[ -f "$KB_F6" ] || python skripte/wissensbasis/baue_zweite_wissensbasis.py daten/quellen/fischer "$KB_F6"
python skripte/wissensbasis/ordne_chunks_zu.py "$FRAGEN_F" "$KB_F6" daten/testfragen/testfragen_fischer_v1_v6.csv
merke "Fischer-KB pypdf + Chunk-Zuordnung" $?

schritt "2 Generierung V6-BOEGE"
python skripte/evaluation/fuehre_testfragen_aus.py V6-BOEGE $RET --scaffolding G-v1
merke "Generierung V6-BOEGE" $?

schritt "3 Generierung V6-FISCHER"
python skripte/evaluation/fuehre_testfragen_aus.py V6-FISCHER $RET --scaffolding G-v1 \
    --kb "$KB_F6" --fragen daten/testfragen/testfragen_fischer_v1_v6.csv
merke "Generierung V6-FISCHER" $?

schritt "4 MinerU-Extraktion + Bildbeschreibungen (VLM) + Wissensbasen v7a/v7b"
modelle_entladen
python skripte/wissensbasis/baue_wissensbasis_struktur.py --pdf "$FISCHER_PDF" --name fischer --methode ocr
merke "Extraktion + VLM + KB v7a/v7b" $?
modelle_entladen
python skripte/wissensbasis/ordne_chunks_zu.py "$FRAGEN_F" "$KB_F7A" daten/testfragen/testfragen_fischer_v1_v7a.csv
python skripte/wissensbasis/ordne_chunks_zu.py "$FRAGEN_F" "$KB_F7B" daten/testfragen/testfragen_fischer_v1_v7b.csv

schritt "5 Generierung V7A-FISCHER und V7B2-FISCHER"
if [ -f "$KB_F7A" ]; then
  python skripte/evaluation/fuehre_testfragen_aus.py V7A-FISCHER $RET --scaffolding G-v1 \
      --kb "$KB_F7A" --fragen daten/testfragen/testfragen_fischer_v1_v7a.csv
  merke "Generierung V7A-FISCHER" $?
fi
if [ -f "$KB_F7B" ]; then
  python skripte/evaluation/fuehre_testfragen_aus.py V7B2-FISCHER $RET --scaffolding G-v1 \
      --kb "$KB_F7B" --fragen daten/testfragen/testfragen_fischer_v1_v7b.csv
  merke "Generierung V7B2-FISCHER" $?
fi
modelle_entladen

schritt "6 RAGAS (Richter mistral-nemo, Prompts J-v1)"
python skripte/evaluation/ragas_auswertung.py V6-BOEGE && python skripte/evaluation/archiviere_version.py V6-BOEGE
merke "RAGAS V6-BOEGE" $?
python skripte/evaluation/ragas_auswertung.py V6-FISCHER --kb "$KB_F6" && python skripte/evaluation/archiviere_version.py V6-FISCHER
merke "RAGAS V6-FISCHER" $?
if [ -f "$KB_F7A" ]; then
  python skripte/evaluation/ragas_auswertung.py V7A-FISCHER --kb "$KB_F7A" && python skripte/evaluation/archiviere_version.py V7A-FISCHER
  merke "RAGAS V7A-FISCHER" $?
fi
if [ -f "$KB_F7B" ]; then
  python skripte/evaluation/ragas_auswertung.py V7B2-FISCHER --kb "$KB_F7B" && python skripte/evaluation/archiviere_version.py V7B2-FISCHER
  merke "RAGAS V7B2-FISCHER" $?
fi
python skripte/evaluation/ragas_auswertung.py V4-S2 --judge-prompts J-v1 && python skripte/evaluation/archiviere_version.py V4-S2 V4-S2_J-v1
merke "RAGAS V4-S2 mit J-v1" $?

schritt "7 Stufen-Check"
python skripte/evaluation/stufen_check.py V4-S2 V6-BOEGE V6-FISCHER V7A-FISCHER V7B2-FISCHER

schritt "Übersicht"
printf '%s\n' "${STATUS[@]}"
echo "Prüfdatei Bildbeschreibungen: daten/extraktion/fischer/bildbeschreibungen_pruefung.csv"

#!/usr/bin/env bash
# HG-v1: Hinweis-Wächter + neuer Fragensatz (v3, 100 Fragen aus Fischer/Böge/außerhalb). Aus ~/RAG, Umgebung pilot_rag, Ollama läuft.
#
#   cd ~/RAG && bash ~/hg_v1/hg_lauf.sh einrichten  # Patch einspielen, Fragensatz kopieren, Dateien prüfen (1 Minute)
#   bash skripte/laeufe/hg_lauf.sh pilot           # 3 Fragen, Wächter an: Funktion und Zeit prüfen (ca. 15-25 min)
#   bash skripte/laeufe/hg_lauf.sh antworten       # neuer Satz (100 Fragen) mit V11B: Antworten ohne und mit RAG (ca. 1,5-2 h)
#   bash skripte/laeufe/hg_lauf.sh dialog_alt      # alter Satz (HD-V2, 92 Dialoge), V11B + Wächter -> Label HD-V3 (mehrere Stunden)
#   bash skripte/laeufe/hg_lauf.sh dialog_neu      # neuer Satz (90 Buchfragen), V11B + Wächter -> Label HD-V3N (mehrere Stunden)
#   bash skripte/laeufe/hg_lauf.sh nacht           # antworten, dialog_alt, dialog_neu hintereinander (über Nacht)
#   bash skripte/laeufe/hg_lauf.sh waechter143     # Wächter + Rubrik P1-P6 auf den 143 gespeicherten HD-V2-Hinweisen (HG-R, ca. 1 h)
#   bash skripte/laeufe/hg_lauf.sh vergleich       # Vergleich HD-V2 gegen HD-V3 und HD-V3N (Wächter vor/nach)
#   bash skripte/laeufe/hg_lauf.sh alles           # EIN BEFEHL ÜBER NACHT: einrichten, Kurztest, waechter143, antworten, dialog_alt, dialog_neu, vergleich, Zip nach Downloads
# Empfehlung: erst einrichten, dann pilot, dann nacht. Jeder Schritt setzt nach Abbruch fort (gleicher Befehl).
cd "${HG_ROOT:-$PWD}" || exit 1
[ -d lernassistent ] || { echo "Bitte aus ~/RAG starten (Ordner lernassistent fehlt)"; exit 1; }
PAKET="${HG_PAKET:-$(cd "$(dirname "$0")" && pwd)}"   # Ordner mit patch_hg_v1.py (entpacktes Paket) bzw. skripte/laeufe
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
KB=daten/wissensbasen/knowledge_base_fischer_boege_v7r.json
TF=daten/testfragen
NEU_F=$TF/testfragen_fischer_v3.csv; NEU_B=$TF/testfragen_boege_v3.csv; NEU_A=$TF/testfragen_ausserhalb_v3.csv
mkdir -p protokolle evaluationsdaten
cmd="${1:?einrichten | pilot | waechter143 | antworten | dialog_alt | dialog_neu | nacht | vergleich | alles}"

einrichten() {
  [ -f "$PAKET/patch_hg_v1.py" ] || { echo "Paket nicht gefunden: $PAKET (HG_PAKET=<Ordner> setzen)"; exit 1; }
  python "$PAKET/patch_hg_v1.py" || exit 1
  cp "$PAKET"/testfragen/testfragen_*_v3.csv "$TF/" && echo "Fragensatz v3 kopiert nach $TF"
  mkdir -p skripte/laeufe && cp "$PAKET/hg_lauf.sh" skripte/laeufe/hg_lauf.sh 2>/dev/null
  [ -f "$KB" ] || echo "WARNUNG: $KB fehlt"
  ls -la "$NEU_F" "$NEU_B" "$NEU_A"
  [ -f evaluationsdaten/hinweis_dialog_HD-V2_zustand.json ] || echo "WARNUNG: HD-V2 fehlt (Vergleich nicht möglich)"
}

dialog() {  # $1 Label  $2 Fragensatz ("alt" oder "neu")  $3 optionale Zusatzargumente
  label="$1"; satz="$2"; shift 2
  export LERNASSISTENT_HG=HG-v1
  if [ "$satz" = "neu" ]; then export HD_FRAGEN="fischer=$NEU_F;boege=$NEU_B"; else unset HD_FRAGEN; fi
  python skripte/evaluation/teste_hinweis_dialog.py --label "$label" "$@"
}

case "$cmd" in
  einrichten) einrichten ;;
  pilot)
    echo "=== Pilot alter Satz (3 Fragen, Wächter an) $(date +%H:%M)"; dialog HD-V3 alt --limit 3
    echo "=== Pilot neuer Satz (3 Fragen, Wächter an) $(date +%H:%M)"; dialog HD-V3N neu --limit 3
    ls -la evaluationsdaten/hinweis_dialog_HD-V3*PILOT* ;;
  antworten)
    export LERNASSISTENT_G=G-v4 LERNASSISTENT_RP=RP-v5 LERNASSISTENT_FS=aus; unset LERNASSISTENT_HG
    echo "Konfiguration V11B: G-v4, RP-v5, FS=aus, Wächter aus"; ollama ps
    for p in "F|$NEU_F" "B|$NEU_B" "A|$NEU_A"; do
      k="${p%%|*}"; f="${p#*|}"
      echo; echo "=== NEU100-$k $(date +%H:%M)"
      python skripte/evaluation/vergleich_mit_ohne_rag.py "RAGVGL-NEU100${k}-V11B" --kb "$KB" --fragen "$f" --ideen '' --retrieval hybrid_kg_rr --judge none --logge
    done
    ls -la evaluationsdaten/vergleich_rag_RAGVGL-NEU100*-V11B.csv ;;
  waechter143) echo "=== HG-R: Wächter + Rubrik auf 143 HD-V2-Situationen $(date +%H:%M)"
    python skripte/evaluation/teste_hinweis_waechter.py "${@:2}" ;;
  dialog_alt) echo "=== Dialog alter Satz, Wächter an $(date +%H:%M)"; dialog HD-V3 alt ;;
  dialog_neu) echo "=== Dialog neuer Satz, Wächter an $(date +%H:%M)"; dialog HD-V3N neu ;;
  nacht)
    bash "$0" antworten  2>&1 | tee "protokolle/hg_antworten_$(date +%Y%m%d_%H%M).txt"
    bash "$0" dialog_alt 2>&1 | tee "protokolle/hg_dialog_alt_$(date +%Y%m%d_%H%M).txt"
    bash "$0" dialog_neu 2>&1 | tee "protokolle/hg_dialog_neu_$(date +%Y%m%d_%H%M).txt"
    bash "$0" vergleich ;;
  alles)
    # Ein Befehl über Nacht. Jede Stufe läuft weiter, auch wenn eine andere scheitert; Fehler stehen am Ende in der Liste.
    ST=$(date +%Y%m%d_%H%M); LOG=protokolle/hg_alles_$ST; mkdir -p "$LOG"; FEHL=""
    stufe() { n="$1"; shift; echo; echo "######## $n  $(date '+%d.%m. %H:%M')"
      "$@" 2>&1 | tee "$LOG/$n.txt"; rc=${PIPESTATUS[0]}
      [ "$rc" -ne 0 ] && { FEHL="$FEHL $n"; echo "!!!! Stufe $n mit Code $rc beendet"; }; return 0; }
    stufe 01_einrichten   bash "$0" einrichten
    stufe 02_kurztest     python skripte/evaluation/teste_hinweis_waechter.py --limit 3
    stufe 03_waechter143  bash "$0" waechter143
    stufe 04_antworten    bash "$0" antworten
    stufe 05_dialog_alt   bash "$0" dialog_alt
    stufe 06_dialog_neu   bash "$0" dialog_neu
    stufe 07_vergleich    bash "$0" vergleich
    echo; echo "######## FERTIG $(date '+%d.%m. %H:%M')   Fehlgeschlagene Stufen:${FEHL:- keine}"
    ZIEL="${HG_ZIEL:-/mnt/c/Users/Vel Narayanasamy/Downloads}"
    ZIP="hg_ergebnisse_$ST.zip"
    zip -rq "$ZIP" "$LOG" evaluationsdaten/hinweis_waechter_HG-R* evaluationsdaten/hinweis_vergleich_* \
        evaluationsdaten/hinweis_dialog_HD-V3* evaluationsdaten/vergleich_rag_RAGVGL-NEU100* 2>/dev/null
    mkdir -p "$ZIEL" 2>/dev/null && cp "$ZIP" "$ZIEL/" && echo "Ergebnisse: $ZIEL/$ZIP" || echo "Zip liegt in $PWD/$ZIP (Ziel nicht schreibbar)" ;;
  vergleich)
    python skripte/evaluation/vergleiche_hinweislaeufe.py HD-V2 HD-V3
    python skripte/evaluation/vergleiche_hinweislaeufe.py HD-V3     # innerhalb: vor/nach Wächter, alter Satz
    python skripte/evaluation/vergleiche_hinweislaeufe.py HD-V3N ;; # innerhalb: neuer Satz
  *) echo "unbekannt: $cmd"; exit 1 ;;
esac

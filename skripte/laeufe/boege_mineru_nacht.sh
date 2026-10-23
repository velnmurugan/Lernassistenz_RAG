#!/usr/bin/env bash
# Böge: MinerU-Extraktion (OCR-Modus wie bei Fischer) + Bildbeschreibungen + Wissensbasis, danach kombinierte
# Wissensbasis Fischer(v7c) + Böge(neu). Nichts Vorhandenes wird überschrieben.
# Start (im Projektordner, Umgebung pilot_rag aktiv, Streamlit-App und andere GPU-Programme geschlossen):
#   mkdir -p protokolle && nohup bash skripte/laeufe/boege_mineru_nacht.sh > protokolle/boege_mineru_$(date +%Y%m%d).txt 2>&1 &
# Fortschritt ansehen:  tail -f protokolle/boege_mineru_*.txt
# Abbrechen und später fortsetzen: Bildbeschreibungen sind fortsetzbar (Cache); die MinerU-Extraktion beginnt neu.
cd "$(dirname "$0")/../.." || exit 1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
T0=$(date +%s)
zeit() { echo; echo "=== $(date +%H:%M:%S)  $1  (seit Start: $(( ($(date +%s)-T0)/60 )) min) ==="; }

BOEGE_PDF=$(ls daten/quellen/boege/*.pdf 2>/dev/null | head -1)
[ -n "$BOEGE_PDF" ] || { echo "FEHLER: keine PDF in daten/quellen/boege/"; exit 1; }
KB_F=daten/wissensbasen/knowledge_base_fischer_v7c.json
[ -f "$KB_F" ] || { echo "FEHLER: $KB_F fehlt"; exit 1; }
echo "PDF: $BOEGE_PDF"
python - <<PY
import pypdf; print("Seiten:", len(pypdf.PdfReader("$BOEGE_PDF").pages))
PY

# GPU frei machen
for m in $(ollama ps 2>/dev/null | awk 'NR>1{print $1}'); do ollama stop "$m"; done

zeit "1 MinerU (ocr) + Bildbeschreibungen + Wissensbasis"
python skripte/wissensbasis/baue_wissensbasis_struktur.py --pdf "$BOEGE_PDF" --name boege --methode ocr
RC=$?
echo "Rückgabewert Schritt 1: $RC"
for m in $(ollama ps 2>/dev/null | awk 'NR>1{print $1}'); do ollama stop "$m"; done

KB_B=$(ls -t daten/wissensbasen/knowledge_base_boege_v7b.json daten/wissensbasen/knowledge_base_boege_v7a.json 2>/dev/null | head -1)
if [ $RC -ne 0 ] || [ -z "$KB_B" ]; then
  echo "FEHLER: keine neue Böge-Wissensbasis gefunden; Schritt 2 entfällt"; zeit "Abbruch"; exit 1
fi
echo "Böge-Wissensbasis: $KB_B"

zeit "2 Kombinierte Wissensbasis Fischer + Böge (neu)"
python skripte/wissensbasis/baue_kombinierte_wissensbasis.py "$KB_F" Fischer "$KB_B" Böge \
    daten/wissensbasen/knowledge_base_fischer_boege_v7.json
echo "Rückgabewert Schritt 2: $?"

zeit "3 Kurzstatistik"
python - <<'PY'
import json, statistics, collections
for p in ["daten/wissensbasen/knowledge_base_fischer_boege.json", "daten/wissensbasen/knowledge_base_fischer_boege_v7.json"]:
    try:
        c = json.load(open(p, encoding="utf-8"))["chunks"]
    except Exception as e:
        print(p, "nicht lesbar:", e); continue
    n = collections.Counter(x.get("buch") for x in c)
    w = {b: statistics.median(len(x["text"].split()) for x in c if x.get("buch") == b) for b in n}
    print(p, dict(n), "Median Wörter/Chunk:", w)
PY
zeit "FERTIG"

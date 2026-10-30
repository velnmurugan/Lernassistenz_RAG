#!/usr/bin/env bash
# Vorab-Prüfsatz V1 (100 Fragen) mit der eingefrorenen Konfiguration V11B – ein Befehl, Vordergrund, Terminal offen lassen.
# Start (aus ~/RAG, Umgebung pilot_rag aktiv):
#   bash skripte/laeufe/vorabsatz_lauf.sh                 (alles: Retrieval + Antworten mit/ohne RAG, ca. 1,5-2 h)
#   bash skripte/laeufe/vorabsatz_lauf.sh nur-retrieval   (nur Recall/MRR, ca. 10-15 min)
# Voraussetzung: vorabsatz_fischer_v1.csv und vorabsatz_boege_v1.csv liegen in Windows-Downloads (oder schon in daten/testfragen/).
# Konfiguration = V11B: G-v4, RP-v5, HP-v4, FS=aus, qwen3.5:9b (T=0, Seed 42), Wissensbasis fischer_boege_v7r, hybrid_kg_rr, Richter none.
# Es wird nichts am Prompt oder Code geändert. Nach dem Lauf auf diesem Satz nichts abstimmen.
MODUS="${1:-alles}"
cd "$(dirname "$0")/../.." || exit 1
[ -d skripte/evaluation ] || { echo "FEHLER: Projektordner nicht gefunden (aus ~/RAG starten)."; exit 1; }
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
mkdir -p protokolle daten/testfragen evaluationsdaten
KB=daten/wissensbasen/knowledge_base_fischer_boege_v7r.json
FQ=daten/testfragen/vorabsatz_fischer_v1.csv
BQ=daten/testfragen/vorabsatz_boege_v1.csv
FC=daten/testfragen/vorabsatz_fischer_v1_chunks.csv
BC=daten/testfragen/vorabsatz_boege_v1_chunks.csv
[ -f "$KB" ] || { echo "FEHLT: $KB"; exit 1; }
command -v ollama >/dev/null || { echo "FEHLER: ollama nicht gefunden."; exit 1; }
ollama list | grep -q "qwen3.5:9b" || { echo "ABBRUCH: qwen3.5:9b fehlt."; exit 1; }
t0=$(date +%s); stunde () { echo "[$(date +%H:%M)] $1 (seit Start $(( ($(date +%s)-t0)/60 )) min)"; }

echo "== 1/6 Fragen einlesen (BOM entfernen) =="
DL=$(ls -d /mnt/c/Users/*/Downloads 2>/dev/null | grep -v -e Public -e Default -e "All Users" | head -1)
for n in vorabsatz_fischer_v1.csv vorabsatz_boege_v1.csv; do
  ziel="daten/testfragen/$n"
  if [ -n "$DL" ] && [ -f "$DL/$n" ]; then sed '1s/^\xEF\xBB\xBF//' "$DL/$n" > "$ziel" && echo "$n aus Downloads übernommen."
  elif [ -f "$ziel" ]; then sed -i '1s/^\xEF\xBB\xBF//' "$ziel"; echo "$n schon in daten/testfragen/."
  else echo "ABBRUCH: $n nicht gefunden (Downloads: ${DL:-nicht erkannt})."; exit 1; fi
done
python - <<'PY' || exit 1
import csv
for f, n in (("daten/testfragen/vorabsatz_fischer_v1.csv", 50), ("daten/testfragen/vorabsatz_boege_v1.csv", 50)):
    r = list(csv.DictReader(open(f, encoding="utf-8")))
    assert len(r) == n and "anker" in r[0] and "nr" in r[0], f
    print(f, len(r), "Fragen, Typen:", {t: sum(z["typ"] == t for z in r) for t in sorted({z["typ"] for z in r})})
PY

echo "== 2/6 Git: Stand sichern =="
if [ -d .git ]; then
  git add -A && git commit -q -m "Stand vor Vorab-Prüfsatz V1" && echo "Commit angelegt." || echo "Nichts zu committen."
  git rev-parse -q --verify refs/tags/vor-vorabsatz >/dev/null && echo "Tag vor-vorabsatz existiert schon." || { git tag vor-vorabsatz && echo "Tag vor-vorabsatz gesetzt."; }
fi

echo "== 3/6 V11B-Konfiguration festnageln =="
unset LERNASSISTENT_CTX LERNASSISTENT_RW LERNASSISTENT_V18 LERNASSISTENT_V19 LERNASSISTENT_MODELL LERNASSISTENT_THINK LERNASSISTENT_TIMEOUT LERNASSISTENT_RB
export LERNASSISTENT_G=G-v4 LERNASSISTENT_RP=RP-v5 LERNASSISTENT_FS=aus
env | grep '^LERNASSISTENT_' | sort
echo "Ollama:"; ollama ps
echo "(Spalte PROCESSOR sollte 100 % GPU zeigen; Browser und andere GPU-Programme schließen, sonst sind die Zeiten nicht vergleichbar.)"

echo "== 4/6 Chunk-Zuordnung über die Anker =="
python skripte/wissensbasis/ordne_chunks_zu.py "$FQ" "$KB" "$FC" | tail -n 12
python skripte/wissensbasis/ordne_chunks_zu.py "$BQ" "$KB" "$BC" | tail -n 12
python - <<'PY'
import csv
for f in ("daten/testfragen/vorabsatz_fischer_v1_chunks.csv", "daten/testfragen/vorabsatz_boege_v1_chunks.csv"):
    r = list(csv.DictReader(open(f, encoding="utf-8")))
    ohne = [z["nr"] for z in r if z["typ"] != "ausserhalb" and not z["chunk_id"]]
    print(f"{f}: ohne Chunk-Zuordnung (ohne ausserhalb): {ohne or 'keine'}")
PY

echo "== 5/6 Retrieval (Recall@4, MRR) =="
stunde "Retrieval Fischer"
python skripte/evaluation/fuehre_testfragen_aus.py "VORABF-V11B-BEIDE" --retrieval hybrid_kg_rr --kb "$KB" --fragen "$FC"
stunde "Retrieval Böge"
python skripte/evaluation/fuehre_testfragen_aus.py "VORABB-V11B-BEIDE" --retrieval hybrid_kg_rr --kb "$KB" --fragen "$BC"

if [ "$MODUS" != nur-retrieval ]; then
  echo "== 6/6 Antworten mit und ohne RAG (Richter none) =="
  stunde "Antworten Fischer (50)"
  python skripte/evaluation/vergleich_mit_ohne_rag.py "RAGVGL-VORABF-V11B-BEIDE7" --kb "$KB" --fragen "$FC" --ideen '' --retrieval hybrid_kg_rr --judge none --logge
  stunde "Antworten Böge (50)"
  python skripte/evaluation/vergleich_mit_ohne_rag.py "RAGVGL-VORABB-V11B-BEIDE7" --kb "$KB" --fragen "$BC" --ideen '' --retrieval hybrid_kg_rr --judge none --logge
fi

echo "== Doku und Git =="
TXT="Vorab-Prüfsatz V1 (30 Oct 2026): 100 frische Fragen (50 Fischer, 50 Böge) aus den Original-PDFs, ohne Überschneidung mit bisherigen Sätzen. Lauf mit V11B (G-v4, RP-v5, FS=aus, qwen3.5:9b, KB v7r) über skripte/laeufe/vorabsatz_lauf.sh; Ergebnisse in evaluationsdaten/ (testlauf_retrieval_VORAB*, vergleich_rag_RAGVGL-VORAB*). Privat, kein Beleg im Beitrag; nichts auf diesem Satz abstimmen."
PA=$(ls PROZESSABLAUF.md doku/PROZESSABLAUF.md docs/PROZESSABLAUF.md 2>/dev/null | head -1)
for f in README.md "$PA"; do
  [ -n "$f" ] && [ -f "$f" ] || { echo "$f nicht gefunden – übersprungen."; continue; }
  grep -q "Vorab-Prüfsatz V1 (30 Oct 2026)" "$f" && echo "$f: Abschnitt schon vorhanden." || { { echo; echo "## Vorab-Prüfsatz V1 (30 Oct 2026)"; echo "$TXT"; } >> "$f"; echo "$f: Abschnitt angehängt."; }
done
if [ -d .git ]; then
  git add -A && git commit -q -m "Vorab-Prüfsatz V1: Fragen und V11B-Lauf" && echo "Commit angelegt." || echo "Nichts zu committen."
fi
stunde "Fertig"
ls -1 evaluationsdaten/testlauf_retrieval_VORAB*-V11B-BEIDE*.csv evaluationsdaten/vergleich_rag_RAGVGL-VORAB*-V11B-BEIDE7*.csv 2>/dev/null

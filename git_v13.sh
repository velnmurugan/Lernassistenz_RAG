#!/usr/bin/env bash
# Git: fehlende Marke v11-rb nachholen (V11b-Stand), dann V13 festhalten. Kein push.
# Start (aus ~/RAG):  bash git_v13.sh            (nach dem Einspielen und den Offline-Tests)
cd "$(dirname "$0")" || exit 1
git status --short | head -20
if ! git rev-parse -q --verify refs/tags/v11-rb >/dev/null; then
  echo "Marke v11-rb fehlt: setze sie auf den letzten Commit vor V13 (HEAD). Falls der V12-Stand schon eingecheckt ist, ggf. vorher prüfen: git log --oneline | head"
  git tag -a v11-rb -m "V11b Rechenbaustein RB-v2 (N100-Lauf V11B)" && echo "v11-rb gesetzt auf $(git rev-parse --short HEAD)"
fi
git add lernassistent skripte evaluationsdaten/n100_v11b_bewertung.csv git_v13.sh
git commit -m "V13: RP-v6 (Einheitenwaechter, Bereinigung), RB-v3 (Parser, Retry, Rueckfall, ungestuetzte Abweichung), G-v5 (L6/L7)" || echo "nichts zu committen"
git tag -a v13 -m "V13 Kandidat (Nachtlauf V13A/V13B auf N100)" 2>/dev/null || echo "Marke v13 existiert schon"
git log --oneline | head -3

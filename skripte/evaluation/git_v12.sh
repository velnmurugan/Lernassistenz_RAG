#!/usr/bin/env bash
# Git für V12: Code committen und taggen, NICHT pushen. Start aus ~/RAG:  bash skripte/evaluation/git_v12.sh [Tag] [Nachricht]
# Aufgenommen werden nur Code und Doku (app.py, lernassistent/, skripte/, doku/), nie evaluationsdaten/ oder daten/ (Buchinhalte).
set -u
TAG="${1:-v12-9}"
MSG="${2:-V12.1-V12.9: Formelsuche FS-v2, RB-v2-Korrekturen, Bildupload im Eingabefeld (BE-v5), Bildabgleich BA-v1 (optional), Tests}"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "kein Git-Repository hier"; exit 1; }
echo "== Branch: $(git branch --show-current) =="; git status --short | head -40
if ! git rev-parse -q --verify "refs/tags/v11-rb" >/dev/null; then
  echo; echo "HINWEIS: Tag v11-rb (V11b) fehlt noch. Letzte Commits:"; git log --oneline | head -8
  echo "Falls der V11b-Stand ein eigener Commit ist:  git tag -a v11-rb <commit> -m 'V11b RB-v2 (kein Push)'"
fi
for pfad in app.py lernassistent skripte doku; do [ -e "$pfad" ] && git add "$pfad"; done
if git diff --cached --quiet; then echo "Nichts zu committen."; else git commit -m "$MSG" && echo "committed"; fi
if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then echo "Tag $TAG existiert schon – nicht überschrieben."; else git tag -a "$TAG" -m "$MSG" && echo "Tag $TAG gesetzt (nicht gepusht)"; fi
git log --oneline | head -3; git tag | tail -5

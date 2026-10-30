#!/bin/bash
# Gibt den Windows-Downloads-Ordner als WSL-Pfad aus (ohne festen Benutzernamen).
p=""
if command -v cmd.exe >/dev/null 2>&1; then
  up=$(cd /mnt/c 2>/dev/null && cmd.exe /c "echo %USERPROFILE%" 2>/dev/null | tr -d '\r')
  [ -n "$up" ] && up=$(wslpath "$up" 2>/dev/null)
  if [ -n "$up" ]; then
    for c in "$up/Downloads" "$up"/OneDrive*/Downloads; do
      [ -d "$c" ] && p="$c" && break
    done
  fi
fi
if [ -z "$p" ]; then
  for c in /mnt/c/Users/*/Downloads; do
    case "$c" in *Public*|*Default*|*"All Users"*) continue;; esac
    [ -d "$c" ] && p="$c" && break
  done
fi
[ -z "$p" ] && p="$HOME"
printf '%s' "$p"

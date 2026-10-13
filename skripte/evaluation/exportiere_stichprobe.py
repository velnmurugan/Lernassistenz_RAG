"""Exportiert eine über Kapitel verteilte Stichprobe sauberer Chunks
zur Erstellung eines Testfragen-Sets (einmaliges Hilfsskript)."""
import sys as _sys, pathlib as _pl  # Projektpfade (lernassistent/pfadsetup.py)
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import json, random, re

random.seed(42)
ANZAHL = 60

with open("daten/wissensbasen/knowledge_base_boege.json", encoding="utf-8") as f:
    chunks = json.load(f)["chunks"]

def ist_sauber(text):
    if not (300 <= len(text) <= 1200):
        return False
    woerter = text.split()
    einzelbuchstaben = sum(1 for w in woerter if len(w) == 1 and w.isalpha())
    return einzelbuchstaben / max(len(woerter), 1) < 0.15  # filtert "Vo l u m e n"

nach_thema = {}
for c in chunks:
    if ist_sauber(c["text"]):
        nach_thema.setdefault(c["thema"], []).append(c)

themen = sorted(nach_thema)
schritt = max(1, len(themen) // ANZAHL)
auswahl = [random.choice(nach_thema[t]) for t in themen[::schritt]][:ANZAHL]

with open("daten/testfragen/stichprobe_testfragen.json", "w", encoding="utf-8") as f:
    json.dump([{k: c.get(k) for k in ("id", "thema", "seite", "text")} for c in auswahl],
              f, ensure_ascii=False, indent=2)

print(f"{len(auswahl)} Chunks aus {len(themen)} Kapiteln exportiert -> stichprobe_testfragen.json")
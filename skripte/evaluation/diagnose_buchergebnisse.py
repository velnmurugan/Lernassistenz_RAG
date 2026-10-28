"""V13.4: Wie stehen Ergebnisse von Buchaufgaben in der Wissensbasis? Zählt Chunks mit Aufgaben, wie viele davon eine
Ergebniszeile haben, die RP-v10 erkennt (rag_pipeline._BUCHERGEBNIS), und zeigt Beispiele mit und ohne Treffer.
Ohne Ollama, ca. 5 s. Start (aus ~/RAG): python skripte/evaluation/diagnose_buchergebnisse.py [KB-Pfad]"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import re
import rag_pipeline as rpl

kb = _sys.argv[1] if len(_sys.argv) > 1 else "daten/wissensbasen/knowledge_base_fischer_boege_v7r.json"
chunks = rpl.lade_wissensbasis(kb)
aufgabe = re.compile(r"\bAufgabe\s*\d+\.\d+")
mit_aufgabe = [c for c in chunks if aufgabe.search(c.get("text", ""))]
treffer = [c for c in mit_aufgabe if rpl.buchergebnisse(c["text"])]
print(f"KB {kb}: {len(chunks)} Chunks, {len(mit_aufgabe)} mit 'Aufgabe x.y', davon {len(treffer)} mit erkannter Ergebniszeile")
print(f"Ergebnisangaben in allen Chunks: {sum(len(rpl.buchergebnisse(c.get('text', ''))) for c in chunks)}")
print("\n--- erkannte Ergebnisangaben (bis 8; nach ‖ der Text, der stehen bleibt):")
for c in treffer[:8] + [c for c in chunks if c not in mit_aufgabe and rpl.buchergebnisse(c.get('text', ''))][:4]:
    t = c["text"]
    print(f"  {c['id']}: {[t[a:b][:100] + ' ‖ ' + t[b:b + 30] for a, b in rpl.buchergebnisse(t)][:3]}")
print("\n--- Aufgaben-Chunks OHNE erkannte Ergebniszeile (bis 6, Text um 'Aufgabe'):")
for c in [c for c in mit_aufgabe if c not in treffer][:6]:
    m = aufgabe.search(c["text"])
    print(f"  {c['id']}: …{c['text'][max(0, m.start() - 80):m.start() + 420]!r}…")
for wort in ("ERG", "Ergebnis", "Lösung", "Lsg", "Antwort"):
    n = sum(1 for c in mit_aufgabe if re.search(rf"\b{wort}", c["text"]))
    print(f"Aufgaben-Chunks mit '{wort}': {n}")

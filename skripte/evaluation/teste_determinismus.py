"""Gibt dieselbe Frage bei T=0/seed 42 immer dieselbe Antwort? A/B-Läufe zeigten, dass der zweite Durchlauf derselben Frage
bei F61, F55, V-1.36 anders ausfiel. Prüft: (a) dreimal direkt hintereinander, (b) mit einer anderen Frage dazwischen.
Start (aus ~/RAG, Ollama läuft):  python skripte/evaluation/teste_determinismus.py | tee evaluationsdaten/determinismus.txt   (ca. 15 min)"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import hashlib, os
os.environ["LERNASSISTENT_FS"] = "aus"
import rag_pipeline as rp
import formelsuche as fs
from vergleich_mit_ohne_rag import lade_fragen
fs.FORMELSUCHE_VERSION = "aus"
rp.RECHEN_PRUEFUNG_VERSION = "RP-v5"
chunks = rp.lade_wissensbasis("daten/wissensbasen/knowledge_base_fischer_boege_v7r.json")
q = {x["nr"]: x["frage"] for x in lade_fragen("daten/testfragen/testfragen_fischer_v2_chunks_beide.csv", "")}
STOER = q["3"]
h = lambda s: hashlib.md5(s.encode()).hexdigest()[:8]
for nr in ("61", "55", "1"):
    print(f"\n=== Frage {nr}")
    a = []
    for i in range(3):
        e = rp.beantworte_frage(q[nr], chunks, methode="hybrid_kg_rr"); a.append(h(e["loesung"]))
    print("direkt hintereinander (3x):", a, "-> identisch" if len(set(a)) == 1 else "-> UNTERSCHIEDLICH")
    b = []
    for i in range(3):
        e = rp.beantworte_frage(q[nr], chunks, methode="hybrid_kg_rr"); b.append(h(e["loesung"]))
        rp.beantworte_frage(STOER, chunks, methode="hybrid_kg_rr")
    print("mit anderer Frage dazwischen (3x):", b, "-> identisch" if len(set(b)) == 1 else "-> UNTERSCHIEDLICH")
    print("direkt = mit Zwischenfrage:", a[0] == b[0])

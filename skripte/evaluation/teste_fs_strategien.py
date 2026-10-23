"""Welche Suchstrategie findet die Formel-Chunks? (echte KB, Ollama). Nur Entwicklungsfälle aus dem App-Test, nicht N100.
Start (aus ~/RAG):  python skripte/evaluation/teste_fs_strategien.py | tee evaluationsdaten/fs_strategien.txt
Je Fall und Strategie: Rang des Ziel-Chunks (1-8) in den Treffern der Anfragen, oder '-' = nicht gefunden."""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import re
import rag_pipeline as rp
import formelsuche as fs

KB = "daten/wissensbasen/knowledge_base_fischer_boege_v7r.json"
TOP = 8
FAELLE = [  # (Name, Frage, Ziel-Chunk-ID-Teil)
    ("1.32 Magnetkran A", "Ein Magnetkran hebt einen Stahlträger mit 2,5 m Länge, Querschnitt 0,02 m² und Dichte 7850 kg/m³. "
     "Welche Flussdichte B muss der Hubmagnet mit der Polfläche A = 0,1 m² mindestens haben?", "pdf_2620"),
    ("1.32 Magnetkran B", "Ein Kran hebt mit einem Hubmagneten einen Stahlträger der Länge 2,5 m, Querschnitt 0,02 m² und Dichte 7850 kg/m³. "
     "Welche Flussdichte B muss der Magnet bei einer Polfläche von 0,1 m² mindestens haben?", "pdf_2620"),
    ("Trafo 40 kVA", "Von einem Drehstrom-Öltransformator 40 kVA, 5000 V / 400 V, Schaltung Yy0 sollen die Bemessungsströme berechnet werden. "
     "Wie groß sind der primäre und der sekundäre Bemessungsstrom?", "fischer_pdf_0873"),
]
P_HYDE = """Schreibe 2 kurze Sätze, wie sie in einem Technik-Lehrbuch stehen und die Formel(n) enthalten, mit denen man diese Aufgabe löst. Keine Zahlen aus der Aufgabe, keine Rechnung, nur die allgemeinen Gleichungen mit Formelzeichen und den Fachbegriffen.

Aufgabe: {f}

Sätze:"""
P_BEGRIFFE = """Nenne 8 Fachbegriffe und Synonyme, die in dem Lehrbuchabschnitt vorkommen, der die Formel zu dieser Aufgabe enthält (Bauteile, Größen, Gesetze). Nur Wörter, durch Komma getrennt, keine Zahlen.

Aufgabe: {f}

Begriffe:"""
P_FRAGE = """Welche Größe wird gesucht und welche allgemeine Gleichung verbindet sie mit den gegebenen Größen? Antworte mit einem Satz im Stil eines Lehrbuchs, ohne Zahlen.

Aufgabe: {f}

Satz:"""
OPT = {"temperature": 0, "seed": 42, "num_predict": 120}
ohne_zahlen = lambda s: re.sub(r"\d+(?:[.,]\d+)?", " ", s)


def strategien(frage):
    s = {}
    s["S0 aktuelle Suchbegriffe (je Begriff)"] = fs.parse(rp.frage_llm(fs.baue_prompt(frage), options=fs.FS_OPTIONEN))
    s["S1 HyDE (Lehrbuchsätze)"] = [z.strip() for z in re.split(r"(?<=[.!?])\s+", rp.frage_llm(P_HYDE.format(f=frage), options=OPT)) if len(z.strip()) > 15][:2]
    b = rp.frage_llm(P_BEGRIFFE.format(f=frage), options=OPT).replace("\n", " ").strip()
    s["S2 Begriffe+Synonyme (eine Anfrage)"] = [ohne_zahlen(b)]
    s["S3 Gesucht/Gleichung (ein Satz)"] = [rp.frage_llm(P_FRAGE.format(f=frage), options=OPT).strip()]
    s["S4 Frage ohne Zahlen"] = [ohne_zahlen(frage)]
    return s


chunks = rp.lade_wissensbasis(KB)
for name, frage, ziel in FAELLE:
    print("=" * 90, f"\n{name} | Ziel {ziel}")
    haupt, _ = rp.retrieval(frage, chunks, top_k=4)
    print("Hauptsuche (Rang des Ziels):", next((i + 1 for i, c in enumerate(haupt) if ziel in c["id"]), "-"))
    for sname, anfragen in strategien(frage).items():
        raenge = []
        for q in anfragen:
            treffer, _ = rp.retrieval(q, chunks, top_k=TOP)
            r = next((i + 1 for i, c in enumerate(treffer) if ziel in c["id"]), "-")
            raenge.append(r)
        print(f"  {sname:<40} Ränge je Anfrage: {raenge}   Anfragen: {[a[:60] for a in anfragen]}")

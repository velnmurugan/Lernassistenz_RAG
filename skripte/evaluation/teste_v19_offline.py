"""Offline-Test V19a (Formelsuche vorab, Schalter LERNASSISTENT_V19=A). Ohne Ollama und ohne Modelle: Modellaufruf, Suche und
Cross-Encoder sind durch kleine Attrappen ersetzt. Prüft Parser, Fusion, Auswahl, Fehlerfälle und den Einbau in die Pipeline.
Start (aus ~/RAG): LERNASSISTENT_V19=A python skripte/evaluation/teste_v19_offline.py   (Modus 'aus': ohne Variable)"""
import sys as _sys, pathlib as _pl, os
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import formelsuche as fs
import rag_pipeline as rpl

ok = fail = 0


def check(name, cond):
    global ok, fail
    ok += bool(cond); fail += (not cond)
    print(("PASS " if cond else "FAIL ") + name)


AN = fs.V19_A
RAW = ("Zuerst Wechselstromwiderstand der Wicklung, dann Strom, dann Verlustleistung.\n### Suchbegriffe\n"
       "1. Induktivität\n2. Impedanz Reihenschaltung R L\n- Stromstärke 230 V\n* Verlustleistung im Widerstand\n")
check("Prompt enthält Aufgabe", "Wicklung" in fs.baue_prompt_weg("Die Wicklung ...?") and "### Suchbegriffe" in fs.baue_prompt_weg("x"))
check("parse_weg: Begriffe nach der Marke, ohne Zahlen", fs.parse_weg(RAW) == ["Induktivität", "Impedanz Reihenschaltung R L", "Verlustleistung im Widerstand"])
check("parse_weg: ohne Marke leer", fs.parse_weg("Impedanz\nInduktivität") == [])
check("parse_weg: leer/None", fs.parse_weg("") == [] and fs.parse_weg(None) == [])
check("fuse_raenge", fs.fuse_raenge([["a", "b", "c"], ["c", "d", "b"]])[:2] == ["c", "b"])

TEXT = {"a": "Z = √(R² + (ω L)²)", "b": "kein Formeltext", "c": "P_v = I² · R", "d": "Beispiel: x = 5 + 3", "e": "Wert = 7 · 2", "h": "I = U / Z"}
CH = [{"id": k, "thema": "t", "score": 0.5, "text": v} for k, v in TEXT.items()]
HAUPT = [CH[4]]  # 'e' ist schon im Kontext


def retr(phrase, chunks, top_k=6, methode=None):
    ordn = {"Induktivität": ["b", "a", "c", "d", "e", "h"], "Impedanz Reihenschaltung R L": ["a", "h", "b", "c", "d", "e"],
            "Verlustleistung im Widerstand": ["c", "d", "a", "b", "e", "h"]}[phrase]
    assert methode == "hybrid_kg", methode  # billige Suche ohne Reranker
    return [], [next(c for c in chunks if c["id"] == i) for i in ordn]


gesehen = {}


def bewerte(query, texte):
    gesehen["query"], gesehen["n"] = query, len(texte)
    return [10.0 if "Z = √" in t else (5.0 if "I = U / Z" in t else 1.0) for t in texte]


z, info = fs.suche_v19("frage?", CH, HAUPT, retr, lambda p, options=None: RAW, bewerte)
check("Auswahl: 2 beste Formel-Chunks, nicht der schon vorhandene", info["ids"] == ["a", "h"] and [c["id"] for c in z] == ["a", "h"])
check("nur Formel-Chunks, die nicht schon im Kontext sind, als Kandidaten (4 von 6)", info["kandidaten"] == 4 and gesehen["n"] == 4)
check("Anfrage = zusammengesetzte Begriffe", gesehen["query"] == "Induktivität Impedanz Reihenschaltung R L Verlustleistung im Widerstand")
check("kein Fehler", info["fehler"] == "")
check("Notiz", "Formelsuche vorab (V19a)" in fs.notiz_v19(info) and "a, h" in fs.notiz_v19(info))

z2, i2 = fs.suche_v19("f", CH, HAUPT, retr, lambda p, options=None: (_ for _ in ()).throw(RuntimeError("ollama aus")), bewerte)
check("Fehler des Modells: kein Zusatz, Fehlertext", z2 == [] and "RuntimeError" in i2["fehler"] and "Fehler" in fs.notiz_v19(i2))
z3, i3 = fs.suche_v19("f", CH, HAUPT, retr, lambda p, options=None: "keine Marke", bewerte)
check("ohne Begriffe: kein Zusatz, kein Fehler", z3 == [] and i3["fehler"] == "")
z4, i4 = fs.suche_v19("f", CH, HAUPT, retr, lambda p, options=None: RAW, lambda q, t: (_ for _ in ()).throw(ValueError("modell")))
check("Fehler des Cross-Encoders: kein Zusatz", z4 == [] and "ValueError" in i4["fehler"])

# Einbau in die Pipeline
RECHEN = "Ein Motor hat R = 4 Ω und L = 0,05 H. Wie groß sind die Verluste bei U = 230 V?"
orig = (fs.suche_v19, rpl.frage_llm, rpl.retrieval)
fs.suche_v19 = lambda frage, chunks, top, r, l, b=None: ([{**CH[0], "fs_phrase": "V19a"}], {"phrasen": ["x"], "ids": ["a"], "kandidaten": 3, "sekunden": 1.0, "fehler": ""})
erg = {"zeiten": {}}
neu = rpl._formelsuche_vorher_v19(RECHEN, CH, [CH[4]], erg, None)
if AN:
    check("Schalter an: Zusatz hinten angefügt, top_chunks im Ergebnis aktualisiert", [c["id"] for c in neu] == ["e", "a"] and erg["top_chunks"] == neu)
    check("Zeit und Info im Ergebnis", erg["zeiten"]["suche"] == 1.0 and erg["formelsuche_v19"]["ids"] == ["a"])
    erg2 = {"zeiten": {}}
    check("keine Rechenfrage: unverändert", rpl._formelsuche_vorher_v19("Was ist ein Kondensator?", CH, [CH[4]], erg2, None) == [CH[4]] and "formelsuche_v19" not in erg2)
    log = []
    rpl._formelsuche_vorher_v19(RECHEN, CH, [CH[4]], {"zeiten": {}}, lambda *a: log.append(a))
    check("Fortschritt: start, ende, quellen", [a[1] for a in log] == ["start", "ende", "quellen"])
else:
    check("Schalter aus: völlig unverändert", neu == [CH[4]] and "formelsuche_v19" not in erg)
fs.suche_v19, rpl.frage_llm, rpl.retrieval = orig
print(f"\n{ok} bestanden, {fail} fehlgeschlagen (Modus {'A' if AN else 'aus'})")
_sys.exit(1 if fail else 0)

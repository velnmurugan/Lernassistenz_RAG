"""FS-v1 mit echter Wissensbasis und echtem Modell (braucht Ollama). Zeigt je aufgabe: Suchbegriffe, ergänzte Chunks,
ob die erwartete Formel darin steht. Start (aus ~/RAG):
  python skripte/evaluation/teste_formelsuche.py | tee evaluationsdaten/formelsuche_test.txt"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import rag_pipeline as rp
import formelsuche as fs

KB = "daten/wissensbasen/knowledge_base_fischer_boege_v7r.json"
# (Name, Frage, Regex der erwarteten Formel im Zusatz- oder Hauptkontext)
AUFGABEN = [
    ("1.32 Magnetkran (Variante)", "Ein Kran hebt mit einem Hubmagneten einen Stahlträger der Länge 2,5 m, Querschnitt 0,02 m² und Dichte 7850 kg/m³. "
     "Welche Flussdichte B muss der Magnet bei einer Polfläche von 0,1 m² mindestens haben?", r"B\s*[²2^].*A|2\s*·?\s*μ"),
    ("1.36 Transformator 400 V", "Ein Transformator hat U1N/U2N = 400 V/100 V und uk = 8 %. Wie groß ist die Sekundärspannung U2 bei rein "
     "ohmscher Last, wenn der ohmsche Spannungsfall vernachlässigt wird?", r"uk|U2|ü"),
    ("Trafo 40 kVA", "Von einem Drehstrom-Öltransformator 40 kVA, 5000 V / 400 V, Yy0 sollen die Bemessungsströme berechnet werden. Wie groß sind I1N und I2N?",
     r"√\s*3|sqrt\(3\)|I\s*1N|I_1N"),
]
chunks = rp.lade_wissensbasis(KB)
print(f"KB: {len(chunks)} Chunks | FS={fs.FORMELSUCHE_VERSION}\n")
for name, frage, erwartet in AUFGABEN:
    print("=" * 80, f"\n{name}\nRechenfrage erkannt: {fs.ist_rechenfrage(frage)}")
    top, _ = rp.retrieval(frage, chunks, top_k=4)
    print("Hauptsuche:", [c["id"] for c in top])
    zusatz, info = fs.suche(frage, chunks, top, rp.retrieval, rp.frage_llm)
    print("Suchbegriffe:", info["phrasen"], "| Sekunden:", info["sekunden"], "| Fehler:", info["fehler"] or "-")
    for c in zusatz:
        print(f"  + {c['id']} (über '{c['fs_phrase']}'): {c['text'][:200].replace(chr(10), ' ')} …")
    import re
    alle = list(top) + zusatz
    in_haupt = any(re.search(erwartet, c.get("text", "")) for c in top)
    in_zusatz = any(re.search(erwartet, c.get("text", "")) for c in zusatz)
    print(f"Erwartete Formel: Hauptsuche={in_haupt} | Zusatz={in_zusatz}")

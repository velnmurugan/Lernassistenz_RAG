"""Warum ist RB-v2 bei manchen Fragen 'nicht verwertbar'? Zeigt Rohausgabe des Modells, Parsing und Grund.
Start (aus ~/RAG, Ollama läuft):  python skripte/evaluation/diagnose_rb2.py | tee evaluationsdaten/diagnose_rb2.txt
Fragen: N100-Nr. 1, 7, 29, 55, 62 + Variante 1.32 (nur Diagnose, kein Prompt-Tuning auf N100)."""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import rag_pipeline as rp
import rechenbaustein as rb
from vergleich_mit_ohne_rag import lade_fragen

NRN = ["1", "7", "29", "55", "62"]
V132 = ("V-1.32", "Ein Magnetkran hebt einen Stahlträger mit 2,5 m Länge, Querschnitt 0,02 m² und Dichte 7850 kg/m³. "
        "Welche Flussdichte B muss der Hubmagnet mit der Polfläche A = 0,1 m² mindestens haben?")
fragen = [(q["nr"], q["frage"]) for q in lade_fragen("daten/testfragen/testfragen_fischer_v2_chunks_beide.csv", "") if q["nr"] in NRN] + [V132]
chunks = rp.lade_wissensbasis("daten/wissensbasen/knowledge_base_fischer_boege_v7r.json")
for nr, frage in fragen:
    print("=" * 90, f"\n[{nr}] {frage}\n")
    top, _ = rp.retrieval(frage, chunks, top_k=4, methode="hybrid_kg_rr")
    kontext = rp._kontext_text(top)
    roh = rp.frage_llm(rb.baue_prompt_v2(frage, kontext), options=rp.GENERIERUNGS_OPTIONEN)
    print("--- Rohausgabe RB-v2 ---\n" + roh)
    parsed = rb.parse_v2(roh)
    print("--- parse_v2 ---", "FORMATFEHLER (None)" if parsed is None else {k: parsed[k] for k in ("rechnung", "werte", "schritte", "ergebnis_namen", "einheit") if k in parsed})
    res = rb.rechne_v2(parsed, frage, kontext)
    print("--- rechne_v2 ---", {k: res.get(k) for k in ("ergebnis", "ergebnisse", "grund", "detail", "formel_im_material")})

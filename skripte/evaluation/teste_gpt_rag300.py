"""Offline-Selbsttest für gpt_rag300.py (ohne KB, ohne Reranker, ohne OpenAI): echter Prompt/Parser aus rag_pipeline.py, Suche und API gemockt."""
import csv, os, sys, tempfile, types, importlib
from pathlib import Path
os.environ["OPENAI_API_KEY"] = "sk-test"; os.environ["LERNASSISTENT_G"] = "G-v6"; os.environ["LERNASSISTENT_RP"] = "RP-v13"
sys.path.insert(0, str(Path(__file__).parent))
import pathlib as _pl
_root = next((p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()), None)
if _root:
    sys.path.insert(0, str(_root / "lernassistent"))
    try:
        import pfadsetup  # noqa: F401
    except Exception:
        pass
import rag_pipeline as rp
import gpt_rag300 as g
ok = True
def check(c, t):
    global ok; ok &= bool(c); print(("OK   " if c else "FEHLER"), t)
CH = [{"id": f"pdf_{i}", "thema": "T", "text": f"Text {i}", "score": 0.9 - i / 10} for i in range(1, 6)]
def fake_ret(frage, chunks, top_k=4, methode=None):
    if "außerhalb" in frage:
        return [], [{"id": "x", "score": 0.1}]
    return CH[:4], CH
rp.retrieval = fake_ret
rp.lade_wissensbasis = lambda p: []
rp.berechne_kb_hash = lambda p: "testhash"
class R:
    status_code = 200
    def __init__(s, t): s.t = t
    def json(s): return {"model": "gpt-test", "choices": [{"message": {"content": s.t}}], "usage": {"prompt_tokens": 1000, "completion_tokens": 50}}
aufrufe = []
def fake_post(url, **k):
    aufrufe.append(k["json"]["messages"][0]["content"])
    return R("STATUS: BEANTWORTET\nLÖSUNG: Nach 5τ.\nÜBERLEGUNG: x\nHINWEIS: Denk an e-Funktion.")
g.requests.post = fake_post
d = tempfile.mkdtemp(); os.chdir(d); os.makedirs("daten/testfragen")
with open("daten/testfragen/fragen300.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["id", "buch", "typ", "frage"]); w.writeheader()
    w.writerow(dict(id="Q1", buch="Fischer", typ="Fakt", frage="Nach wie vielen τ ist C geladen?"))
    w.writerow(dict(id="Q2", buch="Außerhalb", typ="Außerhalb", frage="Frage außerhalb des Materials"))
    w.writerow(dict(id="Q3", buch="Böge", typ="Konzept", frage="Warum?"))
sys.argv = ["x", "--label", "TEST"]
g.main()
z = {r["id"]: r for r in csv.DictReader(open("evaluationsdaten/gptrag300_TEST.csv", encoding="utf-8"))}
check(len(z) == 3 and len(aufrufe) == 2, "3 Fragen, 2 API-Aufrufe (Gate ohne Aufruf)")
check(z["Q1"]["antwort_gpt_rag"] == "Nach 5τ." and z["Q1"]["status_gpt_rag"] == "BEANTWORTET", "Q1: Lösung + Status aus G-v6-Antwort")
check(z["Q2"]["status_gpt_rag"] == "GATE" and "keine ausreichend passende Quelle" in z["Q2"]["antwort_gpt_rag"], "Q2: Gate-Ablehnung wie V20")
check("Text 1" in aufrufe[0] and "Text 4" in aufrufe[0] and "Text 5" not in aufrufe[0], "Prompt enthält genau die ersten 4 Abschnitte")
check("L1 Nutze nur Aussagen" in aufrufe[0] and "L9" in aufrufe[0], "Prompt ist G-v6 (L1…L9)")
check(z["Q1"]["quellen"] == "pdf_1; pdf_2; pdf_3; pdf_4", "Quellen protokolliert")
n = len(aufrufe); g.main()
check(len(aufrufe) == n, "Wiederholung überspringt fertige Fragen (Fortsetzen)")
sys.argv = ["x", "--label", "TEST2", "--nur-prompt", "--limit", "2"]; g.main()
check(len(aufrufe) == n, "--nur-prompt ruft die API nicht auf")
sys.exit(0 if ok else 1)

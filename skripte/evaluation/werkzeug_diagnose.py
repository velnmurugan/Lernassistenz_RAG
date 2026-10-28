"""V14 Diagnose (ca. 3-5 min): Warum ruft das Modell das Rechenwerkzeug nicht auf?
1) Probe-Ergebnisse R12 (RW-v2, RW-v3) aus den CSV-Dateien zeigen.
2) Fähigkeiten des Modells laut Ollama (/api/show: "tools" vorhanden?).
3) Minimaler Werkzeugaufruf ohne Lernmaterial, think aus und an.
4) Minimale Platzhalter-Aufgabe (RW-v3-Regel) ohne Lernmaterial.
Start (aus ~/RAG, pilot_rag):
  python skripte/evaluation/werkzeug_diagnose.py 2>&1 | tee protokolle/werkzeug_diagnose.txt"""
import sys as _sys, pathlib as _pl, csv, time, json
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import requests
import rag_pipeline as rpl

csv.field_size_limit(10**9)
print("=== 1) Probe R12 ===")
for v in ("RW-v2", "RW-v3"):
    p = _pl.Path(f"evaluationsdaten/rechen_varianten_V14K-PROBE-{v}.csv")
    if not p.exists():
        print(v, "keine Datei"); continue
    x = list(csv.DictReader(open(p, encoding="utf-8")))[0]
    print(f"--- {v}: status={x['status']!r} fehler={x['fehler'][:200]!r}")
    print("werkzeug:", x["werkzeug"], "| protokoll:", x["werkzeug_protokoll"][:300])
    print("loesung (Anfang):", repr(x["loesung"][:700]))
    print("loesung_original (Anfang):", repr(x["loesung_original"][:300]))

print("\n=== 2) Modell-Fähigkeiten ===")
basis = rpl.OLLAMA_URL.rsplit("/api/", 1)[0]
try:
    info = requests.post(basis + "/api/show", json={"model": rpl.MODEL_NAME}, timeout=60).json()
    print("capabilities:", info.get("capabilities"))
    vorlage = info.get("template") or ""
    print("Vorlage enthält Tools-Abschnitt:", ".Tools" in vorlage or "tool" in vorlage.lower())
    try:
        print("Ollama-Version:", requests.get(basis + "/api/version", timeout=10).json())
    except Exception as e:
        print("Ollama-Version: ?", e)
except Exception as e:
    print("FEHLER /api/show:", e)

print("\n=== 3) Minimaler Werkzeugaufruf ===")
for think in (False, True):
    t0 = time.time()
    payload = {"model": rpl.MODEL_NAME, "stream": False, "think": think, "options": rpl.GENERIERUNGS_OPTIONEN,
               "tools": [rpl.RW_WERKZEUG],
               "messages": [{"role": "user", "content": "Wie viel ist 23,7 mal 6,1? Benutze das Werkzeug rechne."}]}
    try:
        m = requests.post(rpl.OLLAMA_CHAT_URL, json=payload, timeout=300).json().get("message") or {}
        print(f"think={think}: {time.time()-t0:.0f} s | tool_calls={json.dumps(m.get('tool_calls'), ensure_ascii=False)[:300]}"
              f" | content={m.get('content', '')[:200]!r}")
    except Exception as e:
        print(f"think={think}: FEHLER {e}")

print("\n=== 4) Minimale Platzhalter-Aufgabe (RW-v3) ===")
t0 = time.time()
aufgabe = ("Ein Gerät liegt an U = 230 V und nimmt I = 0,69 A auf. Berechne die Leistung P und die Energie W in 3 h. "
           "Antworte in zwei Sätzen." + rpl.RW3_REGEL)
roh = rpl.frage_llm(aufgabe, options=rpl.GENERIERUNGS_OPTIONEN)
prot = []
text, ok = rpl.rw3_einsetzen(roh, prot)
print(f"{time.time()-t0:.0f} s | ok={ok}")
print("roh:", repr(roh[:500]))
print("eingesetzt:", repr(text[:500]))
print("protokoll:", prot)

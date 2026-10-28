"""Offline-Test V16 (RP-v12 = RP-v11 + drei Zusätze) mit echten Antworten und Nachrechnungen aus V135/V15. Ohne Ollama.
Start (aus ~/RAG): python skripte/evaluation/teste_v16_offline.py"""
import sys as _sys, pathlib as _pl, json
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import rag_pipeline as rpl

ok = fail = 0
def check(name, cond):
    global ok, fail
    ok += bool(cond); fail += (not cond)
    print(("PASS " if cond else "FAIL ") + name)

D = json.load(open(_pl.Path(__file__).with_name("daten_v16.json"), encoding="utf-8"))
CH = [{"id": "c", "thema": "t", "score": 0.6, "text": "Wirkungsgrad η = (P_ab / P_zu) 100 %. P_zu = P_ab / η. Verluste P_v = P_zu - P_ab. W = P · t. K = W · k."}]
def antwort(l, status="BEANTWORTET"): return f"STATUS: {status}\nLÖSUNG: " + l + "\nÜBERLEGUNG: x\nHINWEIS: h"

def lauf(fall, v12, rb_folge, neu=None, status="BEANTWORTET"):
    """rb_folge: Antworten auf Nachrechnungs-Prompts der Reihe nach (erste RB, Bestätigung, Retry …)."""
    folge, auf = list(rb_folge), []
    def llm(p, **k):
        if "Du rechnest eine Aufgabe aus der Technik nach" in p:
            auf.append("rb")
            return folge.pop(0) if folge else "kaputt"
        auf.append("denk" if k.get("denken") else "text")
        return antwort(neu if neu else D[fall]["erste"], status)
    rpl.frage_llm = llm
    rpl.RP_V12 = v12
    q = D[fall]["frage"]
    st = rpl.rechnung_pruefen("…\n### Frage\n" + q + "\n\nAntworte …", {"status": status, "loesung": D[fall]["erste"], "hinweis": "h"}, q, CH)
    return st, auf

alt = rpl.frage_llm, rpl.SCAFFOLDING_VERSION, rpl.RECHEN_PRUEFUNG_VERSION, rpl.NACHRECHNUNG_VERSION, rpl.RP_V12
try:
    rpl.SCAFFOLDING_VERSION, rpl.RECHEN_PRUEFUNG_VERSION, rpl.NACHRECHNUNG_VERSION = "G-v5", "RP-v11", "RB-v7"
    # 1. R01: Kopfsatz angeglichen, Einsparung widerspricht der bestätigten Nachrechnung
    st, _ = lauf("R01", False, [D["R01"]["rb"], D["R01"]["rb"]])
    check("V16 R01 ohne RP-v12: kopf_korrigiert, 960.000 € bleibt (V15)", st["rechen_pruefung"] == "kopf_korrigiert" and "960.000" in st["loesung"][:120])
    st, _ = lauf("R01", True, [D["R01"]["rb"], D["R01"]["rb"]])
    check("V16 R01 RP-v12: Nachrechnung ersetzt (78,95 MW und 31,58 Mio €)", st["rechen_pruefung"] == "ersetzt"
          and "78947368" in st["loesung"].replace(".", "") and "31578947" in st["loesung"].replace(".", ""))
    st, _ = lauf("R01", True, [D["R01"]["rb"], "kaputt", "kaputt"])
    check("V16 R01 RP-v12, Bestätigung scheitert: bleibt kopf_korrigiert", st["rechen_pruefung"] == "kopf_korrigiert")
    # 2. R18: Antwort ohne Ergebnis, Nachrechnung 0,8 Ω
    st, _ = lauf("R18", False, [D["R18"]["rb"], D["R18"]["rb"]], status="TEILWEISE")
    check("V16 R18 ohne RP-v12: unverändert ohne Ergebnis", st["rechen_pruefung"] in ("ok", "bereinigt") and "0,8" not in st["loesung"])
    st, _ = lauf("R18", True, [D["R18"]["rb"], D["R18"]["rb"]], status="TEILWEISE")
    check("V16 R18 RP-v12: bestätigte Nachrechnung gezeigt (0,8 Ω)", st["rechen_pruefung"] == "ersetzt" and "0,8" in st["loesung"][:120])
    st, _ = lauf("R18", True, [D["R18"]["rb"], "kaputt", "kaputt"], status="TEILWEISE")
    check("V16 R18 RP-v12, nicht bestätigt: unverändert", st["rechen_pruefung"] != "ersetzt")
    # 3. F61: zweite Nachrechnung unlesbar -> Retry
    RB_RETRY = ("FORMEL: J = J0 + J1 * (n1/n)**2\nWERTE:\nJ0 = 0,02 kgm²\nJ1 = 1,5 kgm²\nverh = 0,1\nRECHNUNG:\nJ = J0 + J1 * verh**2\n"
                "ERGEBNIS: J\nEINHEIT: kgm²\nQUELLE: J = J₀ + J₁ ((n₁)/n)²")
    NEU61 = "Das umgerechnete Trägheitsmoment beträgt 0,035 kgm². Rechnung: J = 0,02 kgm² + 1,5 kgm² · (1/10)² = 0,035 kgm²."
    st, auf = lauf("F61", False, [D["F61"]["rb"], D["F61"]["rb2"], RB_RETRY], neu=NEU61)
    check("V16 F61 ohne RP-v12: Bestätigung unlesbar -> abweichung_ungestuetzt (V15)", st["rechen_pruefung"] == "abweichung_ungestuetzt")
    st, auf = lauf("F61", True, [D["F61"]["rb"], D["F61"]["rb2"], RB_RETRY], neu=NEU61)
    check("V16 F61 RP-v12: Retry der Bestätigung -> bestätigt, 0,035", "Retry nach" in st["rechen_befund"] and "Bestätigung: ja" in st["rechen_befund"]
          and "0,035" in st["loesung"][:80] and auf.count("rb") == 3)
    # 4. Schalter
    import importlib, os
    os.environ["LERNASSISTENT_RP"] = "RP-v12"
    m = importlib.reload(rpl)
    check("V16 Schalter: LERNASSISTENT_RP=RP-v12 -> intern RP-v11 + RP_V12", m.RP_V12 is True and m.RECHEN_PRUEFUNG_VERSION == "RP-v11")
    os.environ["LERNASSISTENT_RP"] = "RP-v11"
    m = importlib.reload(rpl)
    check("V16 Standard: RP-v11 ohne Zusätze", m.RP_V12 is False)
finally:
    rpl.frage_llm, rpl.SCAFFOLDING_VERSION, rpl.RECHEN_PRUEFUNG_VERSION, rpl.NACHRECHNUNG_VERSION, rpl.RP_V12 = alt
print(f"\n{ok} bestanden, {fail} fehlgeschlagen")
_sys.exit(1 if fail else 0)

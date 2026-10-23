"""Offline test RB-v1 / RP-v4 (no Ollama): simulated model, real N100 failure cases. Start: python skripte/evaluation/teste_rb_offline.py"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import rag_pipeline as rpl
import rechenbaustein as rb

ok = fail = 0
def check(name, cond):
    global ok, fail
    ok += cond; fail += (not cond)
    print(("PASS " if cond else "FAIL ") + name)

# --- unit: evaluator safety and parsing
check("safe: import blocked", rb.sicher_auswerten("__import__('os')") is None)
check("safe: attribute blocked", rb.sicher_auswerten("(1).real") is None)
check("safe: huge power blocked", rb.sicher_auswerten("2**99") is None)
check("safe: comma decimal", abs(rb.sicher_auswerten("0,5*4") - 2.0) < 1e-9)
check("value expr with pi and unit", abs(rb._wert_ausdruck("2*pi*1000/60 1/s")[1] - 104.7198) < 1e-3)
check("value expr unit only 'kg'", rb._wert_ausdruck("500 kg")[1] == 500)

F62 = "Eine Last von 500 kg bewegt sich mit 0,5 m/s geradlinig; der Motor dreht mit 1000 1/min. Welches Ersatzträgheitsmoment?"
RB62 = "FORMEL: Je = m (v/w)^2\nWERTE:\nm = 500 kg\nv = 0,5 m/s\nw = 2*pi*1000/60 1/s\nRECHNUNG: m*(v/w)**2\nEINHEIT: kg*m^2"
res = rb.rechne(rb.parse(RB62), F62, "")
check("nr62 computed 0,0114", res["ergebnis"] and abs(res["ergebnis"] - 0.011399) < 1e-5)
check("nr62 wrong answer flagged", bool(rb.vergleiche("Das Ersatzträgheitsmoment beträgt 0,25 kg·m².", F62, res)))
check("nr62 right answer passes", not rb.vergleiche("Das Ersatzträgheitsmoment beträgt 0,0114 kg·m².", F62, res))
check("percent form passes", not rb.vergleiche("Der Schlupf beträgt 5 %.", "Ein Motor 1425 1/min", {"ergebnis": 0.05, "rechnung": "s"}))
check("kilo factor passes", not rb.vergleiche("Die Leistung beträgt 31,4 kW.", "0,2 l/s", {"ergebnis": 31400.0, "rechnung": "P"}))
inv = rb.rechne(rb.parse("WERTE:\nx = 77\nRECHNUNG: x*2\nEINHEIT: V"), "Frage 5 V", "Kontext 3 A")
check("invented number rejected", inv["ergebnis"] is None and inv["grund"] == "erfunden")
check("KEINE handled", rb.rechne(rb.parse("RECHNUNG: KEINE"), "x", "")["grund"] == "keine_rechnung")
check("format error handled", rb.rechne(rb.parse("Blabla"), "x", "")["grund"] == "formatfehler")

# --- pipeline flow with simulated model
chunk = {"id": "c1", "thema": "t", "text": "Bei gleicher Bewegungsenergie gilt Je = m (v/ω)²."}
def stufen_falsch():
    return {"status": "BEANTWORTET", "loesung": "Das Ersatzträgheitsmoment beträgt 0,25 kg·m². Berechnung mit ω = 1047 1/s.",
            "hinweis": "h", "hinweis_ueberlegung": "", "vollstaendig_geparst": True, "format_fehler": ""}
GOOD = ("STATUS: BEANTWORTET\nLÖSUNG: Das Ersatzträgheitsmoment beträgt 0,0114 kg·m². Mit ω = 2π·1000/60 = 104,7 1/s "
        "und Je = 500 · (0,5 / 104,7)² = 0,0114.\nÜBERLEGUNG: x\nHINWEIS: Denk an die Bewegungsenergie.")
BAD = GOOD.replace("0,0114", "0,25")
def lauf(rb_antwort, neu_antwort, version="RP-v4"):
    aufrufe = []
    def fake(prompt, model=None, options=None):
        aufrufe.append(prompt)
        return rb_antwort if prompt.startswith("Du rechnest eine Aufgabe") else neu_antwort
    alt = (rpl.frage_llm, rpl.RECHEN_PRUEFUNG_VERSION)
    rpl.frage_llm, rpl.RECHEN_PRUEFUNG_VERSION = fake, version
    try:
        st = stufen_falsch()
        rpl.rechnung_pruefen("prompt", st, F62, [chunk])
    finally:
        rpl.frage_llm, rpl.RECHEN_PRUEFUNG_VERSION = alt
    return st, aufrufe

st, calls = lauf(RB62, GOOD)
check("RP-v4 nachgebessert", st["rechen_pruefung"] == "nachgebessert" and "0,0114" in st["loesung"])
check("original kept in log", "0,25" in st["loesung_original"])
check("2 extra calls (RB + rewrite)", len(calls) == 2)
st, calls = lauf(RB62, BAD)
check("rewrite still wrong -> markiert", st["rechen_pruefung"] == "markiert" and "Python-Nachrechnung" in st["loesung"])
st, calls = lauf("RECHNUNG: KEINE", GOOD)
check("RB keine_rechnung -> unchanged, 1 call", st["rechen_pruefung"] == "ok" and len(calls) == 1 and "nicht verwertbar" in st["rechen_befund"])
st, calls = lauf(RB62, GOOD, version="RP-v3")
check("RP-v3 unchanged (no RB call, wrong answer passes)", len(calls) == 0 and st["rechen_pruefung"] == "ok")
st = {"status": "BEANTWORTET", "loesung": "Das Ersatzträgheitsmoment beträgt 0,0114 kg·m².", "hinweis": "h",
      "hinweis_ueberlegung": "", "vollstaendig_geparst": True, "format_fehler": ""}
alt = (rpl.frage_llm, rpl.RECHEN_PRUEFUNG_VERSION)
rpl.frage_llm, rpl.RECHEN_PRUEFUNG_VERSION = (lambda p, model=None, options=None: RB62), "RP-v4"
try:
    rpl.rechnung_pruefen("prompt", st, F62, [chunk])
finally:
    rpl.frage_llm, rpl.RECHEN_PRUEFUNG_VERSION = alt
check("correct answer passes, no rewrite", st["rechen_pruefung"] == "ok" and st["loesung_original"] == "")
st = {"status": "BEANTWORTET", "loesung": "Die Spannung beträgt 400 V.", "hinweis": "h", "hinweis_ueberlegung": "",
      "vollstaendig_geparst": True, "format_fehler": ""}
calls = []
alt = (rpl.frage_llm, rpl.RECHEN_PRUEFUNG_VERSION)
rpl.frage_llm, rpl.RECHEN_PRUEFUNG_VERSION = (lambda p, model=None, options=None: calls.append(p) or ""), "RP-v4"
try:
    rpl.rechnung_pruefen("prompt", st, "Welche Spannung liegt zwischen zwei Außenleitern?", [chunk])
finally:
    rpl.frage_llm, rpl.RECHEN_PRUEFUNG_VERSION = alt
check("question without digit: no RB call", len(calls) == 0)
print(f"\n{ok} passed, {fail} failed")
_sys.exit(1 if fail else 0)

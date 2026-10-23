"""Offline test RB-v2 / RP-v5 (no Ollama): simulated model, live-test failure cases of 21 Oct 2026.
Start (from ~/RAG): python skripte/evaluation/teste_rb2_offline.py"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import rag_pipeline as rpl
import rechenbaustein as rb
import rechenpruefung as rp

ok = fail = 0
def check(name, cond):
    global ok, fail
    ok += bool(cond); fail += (not cond)
    print(("PASS " if cond else "FAIL ") + name)

F40 = ("Von einem Drehstrom-Öltransformator 40kVA, 5.000 V +- 4% / 400V, Schaltung Yy0 sollen die wichtigsten Größen "
       "ermittelt werden. Erhält man den primären und sekundären Bemessungsstrom")
KONTEXT = ("Der Bemessungsstrom ergibt sich aus Gl. (4.30): I1N = SN / (√3 · U1N) und I2N = SN / (√3 · U2N). "
           "Beispiel 4.10: Ein Transformator 50 kVA, 10 kV / 400 V hat I1N = 2,89 A und I2N = 72 A.")
chunk = {"id": "c1", "thema": "t", "text": KONTEXT}

RB_OK = ("FORMEL: I = S / (sqrt(3) * U)\nQUELLE: I1N = SN / (√3 · U1N)\nWERTE:\nS = 40000 VA\nU1N = 5000 V\nU2N = 400 V\n"
         "RECHNUNG:\nI1N = S/(sqrt(3)*U1N)\nI2N = S/(sqrt(3)*U2N)\nERGEBNIS: I1N, I2N\nEINHEIT: A, A")
RB_GRUND = RB_OK.replace("QUELLE: I1N = SN / (√3 · U1N)", "QUELLE: GRUNDWISSEN")
RB_GLNR = RB_OK.replace("QUELLE: I1N = SN / (√3 · U1N)", "QUELLE: Gl. 4.30")
KOPF_FALSCH = "Der primäre Bemessungsstrom beträgt 2,89 A und der sekundäre Bemessungsstrom 72 A."
KOPF_RICHTIG = "Der primäre Bemessungsstrom beträgt 4,62 A und der sekundäre Bemessungsstrom 57,7 A."
KOPF_TEIL = "Der primäre Bemessungsstrom beträgt 4,62 A und der sekundäre Bemessungsstrom 72 A."
WEG = ("\n\nBegründung: Nach Gl. 4.30 gilt I_1N = (S_N)/(√3 U_1N) und I_2N = (S_N)/(√3 U_2N). Rechenweg: "
       "I_1N = (40 kVA) / (√3 · 5 kV) = 4,62 A; I_2N = (40 kVA) / (√3 · 0,4 kV) = 57,7 A")

def rewrite_text(kopf):
    return f"STATUS: BEANTWORTET\nLÖSUNG: {kopf}{WEG}\nÜBERLEGUNG: x\nHINWEIS: Denk an die Formel."

# --- parse_v2
p = rb.parse_v2(RB_OK)
check("parse: two steps", [n for n, _ in p["schritte"]] == ["I1N", "I2N"])
check("parse: result names", p["ergebnis_namen"] == ["I1N", "I2N"])
check("parse: einheit kept", p["einheit"] == "A, A" and p["quelle"].startswith("I1N"))
check("parse: legacy single expression", rb.parse_v2("RECHNUNG: 40000/(sqrt(3)*5000)\nEINHEIT: A")["schritte"][0][0] == "ergebnis")
check("parse: KEINE", rb.parse_v2("RECHNUNG: KEINE")["rechnung"] == "KEINE")
check("parse: no RECHNUNG -> None", rb.parse_v2("Blabla") is None)
check("parse: ERGEBNIS missing -> last step", rb.parse_v2("WERTE:\na = 2\nRECHNUNG:\nb = a*2\nc = b+1\nEINHEIT: V")["ergebnis_namen"] == ["c"])

# --- rechne_v2
res = rb.rechne_v2(p, F40, KONTEXT)
check("rechne: I1N 4,619", abs(res["ergebnisse"][0][1] - 4.6188) < 1e-3)
check("rechne: I2N 57,74", abs(res["ergebnisse"][1][1] - 57.735) < 1e-3)
check("rechne: ergebnis_text", rb.ergebnis_text(res) == "I1N = 4,619 A; I2N = 57,74 A")
check("rechne: invented number rejected", rb.rechne_v2(rb.parse_v2(RB_OK.replace("U1N = 5000", "U1N = 7777")), F40, KONTEXT)["grund"] == "erfunden")
check("rechne: bad step -> auswertung", rb.rechne_v2(rb.parse_v2(RB_OK.replace("sqrt(3)*U2N", "foo(3)")), F40, KONTEXT)["grund"] == "auswertung")

# --- Formelquelle
check("quelle: verbatim", rb.quelle_im_material("I1N = SN / (√3 · U1N)", KONTEXT) is True)
check("quelle: paraphrase (spacing, symbols)", rb.quelle_im_material("I_1N = S_N/(√3·U_1N)", KONTEXT) is True)
check("quelle: Gl. number", rb.quelle_im_material("Gl. 4.30", KONTEXT) is True)
check("quelle: wrong Gl. number", rb.quelle_im_material("Gl. 9.99", KONTEXT) is False)
check("quelle: GRUNDWISSEN", rb.quelle_im_material("GRUNDWISSEN", KONTEXT) is False)
check("quelle: invented formula", rb.quelle_im_material("P = U² · I · cos φ · 7", KONTEXT) is False)
check("quelle: empty -> None", rb.quelle_im_material("", KONTEXT) is None)

# --- vergleiche_v2
check("compare: copied example numbers flagged", bool(rb.vergleiche_v2(KOPF_FALSCH, F40, res)))
check("compare: right answer passes", not rb.vergleiche_v2(KOPF_RICHTIG, F40, res))
check("compare: one wrong of two flagged (units)", bool(rb.vergleiche_v2(KOPF_TEIL, F40, res)))
check("compare: number without unit exempt", not rb.vergleiche_v2("Bei 3 Phasen beträgt der primäre Strom 4,62 A.", F40, res))
check("compare: question values exempt", not rb.vergleiche_v2("Bei 400 V beträgt der Strom 57,7 A.", F40, res))
check("compare: v1 would miss partial", not rb.vergleiche(KOPF_TEIL, F40, {"ergebnis": 4.6188, "rechnung": "x"}))
check("compare: finding text lists both results", "I1N = 4,619 A; I2N = 57,74 A" in rb.vergleiche_v2(KOPF_FALSCH, F40, res)[0]["text"])

# --- RP-v5 checks: no noise from I_1N
noise = [b["text"] for b in rp.pruefe(KOPF_RICHTIG + WEG, F40, "RP-v5")]
check("rp-v5: right answer without findings", noise == [])
noise3 = [b["text"] for b in rp.pruefe(KOPF_RICHTIG + WEG, F40, "RP-v3")]
check("rp-v3 unchanged (noise 'nicht 1' still there)", any("nicht 1" in t for t in noise3))

# --- pipeline flows
def stufen_start(kopf):
    return {"status": "BEANTWORTET", "loesung": kopf + WEG, "hinweis": "h", "hinweis_ueberlegung": "",
            "vollstaendig_geparst": True, "format_fehler": ""}
def lauf(rb_antwort, neu_antwort, kopf, version="RP-v5", frage=F40):
    aufrufe = []
    def fake(prompt, model=None, options=None):
        aufrufe.append(prompt)
        return rb_antwort if prompt.startswith("Du rechnest eine Aufgabe") else neu_antwort
    alt = (rpl.frage_llm, rpl.RECHEN_PRUEFUNG_VERSION)
    rpl.frage_llm, rpl.RECHEN_PRUEFUNG_VERSION = fake, version
    try:
        st = stufen_start(kopf)
        rpl.rechnung_pruefen("prompt", st, frage, [chunk])
    finally:
        rpl.frage_llm, rpl.RECHEN_PRUEFUNG_VERSION = alt
    return st, aufrufe

# a) wrong headline, rewrite repeats the error -> replaced by verified calculation
st, calls = lauf(RB_OK, rewrite_text(KOPF_FALSCH), KOPF_FALSCH)
check("a) replaced", st["rechen_pruefung"] == "ersetzt")
check("a) verified values in solution", "4,619" in st["loesung"] and "57,74" in st["loesung"] and "2,89" not in st["loesung"].split("Begründung")[0])
check("a) original kept in log", "2,89" in st["loesung_original"])
check("a) note visible", "wich von der Nachrechnung ab" in st["loesung"])
check("a) log has RB-v2 line", "RB-v2 Ergebnis I1N = 4,619 A" in st["rechen_befund"] and "Formel im Material" in st["rechen_befund"])
check("a) replaced text passes all checks", not rp.pruefe(st["loesung"].split("\n\n⚠")[0], F40, "RP-v5")
      and not rb.vergleiche_v2(st["loesung"].split("\n\n⚠")[0], F40, res))
# b) rewrite fixes it
st, calls = lauf(RB_OK, rewrite_text(KOPF_RICHTIG), KOPF_FALSCH)
check("b) nachgebessert", st["rechen_pruefung"] == "nachgebessert" and "4,62 A" in st["loesung"])
check("b) 2 extra calls", len(calls) == 2)
# c) formula not in material -> marked, not replaced
st, _ = lauf(RB_GRUND, rewrite_text(KOPF_FALSCH), KOPF_FALSCH)
check("c) marked (formula unverified)", st["rechen_pruefung"] == "markiert" and "Nachrechnung" in st["loesung"] and "Formel nicht im Material" in st["rechen_befund"])
check("c) wrong headline still there but visibly flagged", KOPF_FALSCH in st["loesung"] and "⚠ Automatische Prüfung" in st["loesung"])
# d) right answer untouched
st, calls = lauf(RB_OK, "", KOPF_RICHTIG)
check("d) ok", st["rechen_pruefung"] == "ok" and len(calls) == 1)
check("d) log keeps RB-v2 result", st["rechen_befund"].startswith("RB-v2 Ergebnis"))
# e) partly wrong
st, _ = lauf(RB_GLNR, rewrite_text(KOPF_TEIL), KOPF_TEIL)
check("e) partly wrong replaced (Gl. number as source)", st["rechen_pruefung"] == "ersetzt")
# f) not a calculation
st, calls = lauf("RECHNUNG: KEINE", "", KOPF_FALSCH)
check("f) KEINE -> only RP-v3-level checks (RB call + rewrite), reason logged", len(calls) == 2 and "keine_rechnung" in st["rechen_befund"])
check("names with digits (I1N) are not numbers", rb._kopf_mit_einheit("I1N = 4,62 A und I2N = 57,7 A.", F40) and [k[2] for k in rb._kopf_mit_einheit("I1N = 4,62 A und I2N = 57,7 A.", F40)] == ["4,62", "57,7"])
# g) RP-v4 unchanged
st, calls = lauf("FORMEL: x\nWERTE:\nS = 40000 VA\nRECHNUNG: S/(sqrt(3)*5000)\nEINHEIT: A", rewrite_text(KOPF_RICHTIG), KOPF_FALSCH, version="RP-v4")
check("g) RP-v4 still works (v1 prompt)", st["rechen_pruefung"] in ("nachgebessert", "markiert"))
# h) 98 V case (right formula in RB): wrong headline replaced
F98 = ("Ein Transformator für U1N/U2N = 400 V/100 V hat eine Kurzschlussspannung von uk = 8 %. Wie groß ist bei rein ohmschem "
       "Primärstrom I1N die Sekundärspannung U2, wenn der ohmsche Spannungsfall vernachlässigt wird?")
RB98 = ("FORMEL: U2 = U2N * sqrt(1 + uk^2)\nQUELLE: Gl. 4.30\nWERTE:\nU2N = 100 V\nuk = 8/100\nRECHNUNG:\nU2 = U2N*sqrt(1+uk**2)\n"
        "ERGEBNIS: U2\nEINHEIT: V")
def stufen98():
    return {"status": "BEANTWORTET", "loesung": "Die Sekundärspannung U2 beträgt 98 V.\n\nBegründung: ...", "hinweis": "h",
            "hinweis_ueberlegung": "", "vollstaendig_geparst": True, "format_fehler": ""}
def fake98(prompt, model=None, options=None):
    return RB98 if prompt.startswith("Du rechnest eine Aufgabe") else "STATUS: BEANTWORTET\nLÖSUNG: Die Sekundärspannung U2 beträgt 98 V.\nHINWEIS: h"
alt = (rpl.frage_llm, rpl.RECHEN_PRUEFUNG_VERSION)
rpl.frage_llm, rpl.RECHEN_PRUEFUNG_VERSION = fake98, "RP-v5"
try:
    st = stufen98(); rpl.rechnung_pruefen("prompt", st, F98, [chunk])
finally:
    rpl.frage_llm, rpl.RECHEN_PRUEFUNG_VERSION = alt
check("h) 98 V replaced by 100,3 V", st["rechen_pruefung"] == "ersetzt" and "100,3" in st["loesung"])

# --- model failure never blocks the answer
def kaputt(prompt, model=None, options=None):
    raise RuntimeError("Ollama weg")
alt = (rpl.frage_llm, rpl.RECHEN_PRUEFUNG_VERSION)
rpl.frage_llm, rpl.RECHEN_PRUEFUNG_VERSION = kaputt, "RP-v5"
try:
    st = stufen_start(KOPF_FALSCH); rpl.rechnung_pruefen("prompt", st, F40, [chunk])
finally:
    rpl.frage_llm, rpl.RECHEN_PRUEFUNG_VERSION = alt
check("LLM error: answer kept, RP-v3-level finding marks it", st["loesung"].startswith(KOPF_FALSCH) and st["rechen_pruefung"] in ("markiert", "ok"))

print(f"\n{ok} passed, {fail} failed")
_sys.exit(1 if fail else 0)

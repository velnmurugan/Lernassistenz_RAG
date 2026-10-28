"""Offline-Test V13.3 (RP-v9: Denkmodus, strenge Bestätigung; Kontextfenster). Ohne Ollama. Fälle aus N100 (V11B-Lauf 21 Okt, V12.9-Lauf 24 Okt).
Start (aus ~/RAG): python skripte/evaluation/teste_v133_offline.py"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import rag_pipeline as rpl
import rechenpruefung as rp

ok = fail = 0
def check(name, cond):
    global ok, fail
    ok += bool(cond); fail += (not cond)
    print(("PASS " if cond else "FAIL ") + name)

# Käfigläufer-Fall, App-Läufe 26.10.2026 (18:02 Log, 18:15 Denkmodus-Test C)
FRAGE = ("Ein Käfigläufermotor (50 Hz, synchrone Drehzahl 1500 min⁻¹) hat bei 20 °C den Kippschlupf sK = 0,25 und bei "
         "Bemessungsmoment MN die Drehzahl nN = 1455 min⁻¹. Der Läuferkäfig aus Aluminium erwärmt sich im Betrieb auf 150 °C. "
         "Welche Drehzahl hat der Motor im betriebswarmen Zustand bei MN?")
MATERIAL = ("4.9 Aus Gl. 4.34 Schlupf bei 20°C s = 1 - 1440 min⁻¹ / 1500 min⁻¹ = 0,04 Bei jeweils gleichem Drehmoment M_N müssen in "
            "Gl. 4.41 die Nenner gleich sein, was die Beziehung s_K / s + s / s_K = s_Kw / s_w + s_w / s_Kw ergibt. Mit s = 0,04, "
            "s_K = 0,2, s_Kw = 0,33 entsteht die quadratische Gleichung s_w² - 1,716 s_w + 0,109 = 0 mit der Lösung s_w = 0,066 "
            "Dies ergibt bei M_N die Drehzahl n_Nw = 1500 min⁻¹ (1 - 0,066) = 1401 min⁻¹. Mit Gl. 1.12b und ϑ0 = 225 °C für "
            "Aluminium erhält man Rrw/Rr = (225 + ϑw)/(225 + ϑu).")
CHUNK = {"id": "fischer_pdf_1259", "thema": "Berechnung der Aufgaben", "score": 0.6, "text": MATERIAL}
ERSTE = ("Die Drehzahl im betriebswarmen Zustand beträgt 1420 min⁻¹.\nBegründung: Der Widerstand steigt, s = 1 - 1455/1500 = 0,03. "
         "Der neue Schlupf ergibt sich aus Gl. 4.41.")
WIEDER_1401 = ("Die Drehzahl des Motors im betriebswarmen Zustand beträgt 1401 min⁻¹. Der Widerstand des Aluminiumkäfigs steigt, "
               "wodurch sich der Kippschlupf erhöht; es ergibt sich ein neuer Schlupf s_w, der zu einer niedrigeren Drehzahl führt.")
DENK = ("Die Drehzahl im betriebswarmen Zustand beträgt n_Nw = 1431 min⁻¹.\nBegründung:\n1. Widerstandsverhältnis: "
        "(225 + 150)/(225 + 20) = 375/245 ≈ 1,53.\n2. Neuer Kippschlupf: s_Kw = 1,53 · 0,25 ≈ 0,383.\n3. Schlupf bei 20°C: "
        "s = 1 - 1455/1500 = 0,03.\n4. Aus s_K/s + s/s_K = s_Kw/s_w + s_w/s_Kw folgt die quadratische Gleichung: "
        "s_w² - 3,23 · s_w + 0,146 = 0. Lösung: s_w ≈ 0,046.\n5. n_Nw = 1500 min⁻¹ · (1 - 0,046) = 1431 min⁻¹.")
RB_1399 = ("FORMEL: s_w = s_Kw*s_K/(s_K + 1/s_K)*(s_Kw + 1/s_Kw); n_Nw = n_s*(1 - s_w)\nWERTE:\ns_K = 0.25\nf = (225 + 150)/(225 + 20)\n"
           "n_s = 1500 1/min\nRECHNUNG:\ns_Kw = f*s_K\ns_w = s_Kw*s_K/(s_K + 1/s_K)*(s_Kw + 1/s_Kw)\nn_Nw = n_s*(1 - s_w)\n"
           "ERGEBNIS: n_Nw\nEINHEIT: 1/min\nQUELLE: s_K / s + s / s_K = s_Kw / s_w + s_w / s_Kw")
def antwort(l): return "STATUS: BEANTWORTET\nLÖSUNG: " + l + "\nÜBERLEGUNG: x\nHINWEIS: h"
PROMPT = "…\n### Frage\n" + FRAGE + "\n\nAntworte genau …"

# --- 1. strenge Bestätigung
res = {"ergebnisse": [("n_Nw", 1399.2)], "formel_im_material": True}
check("V13.3 1401 gegen Nachrechnung 1399: v8 (0,5 %) bestätigt, v9 streng nicht",
      rpl._baustein_bestaetigt_kopf(WIEDER_1401, FRAGE, res) and not rpl._baustein_bestaetigt_kopf(WIEDER_1401, FRAGE, res, streng=True))
check("V13.3 streng: 0,506 gegen 0,5058 bestätigt (gerundet gleich)",
      rpl._baustein_bestaetigt_kopf("Das spezifische Volumen beträgt 0,506 m³/kg.", "12 kg, 1,977 kg/m³?", {"ergebnisse": [("v", 0.50582)]}, streng=True))

# --- 2. Denkmodus-Antwort besteht die eigene Prüfung
check("V13.3 Denkmodus-Antwort (1431) ohne Befund (RP-v9)", not [b for b in rp.pruefe(DENK, FRAGE, "RP-v9")] and not rp.pruefe_uebernahme(DENK, FRAGE, MATERIAL))

# --- 3. Ablauf: wie Log 18:02, jetzt mit RP-v9
def lauf(version, denk_antwort, rb_bestaetigung="kaputt"):
    aufrufe = []
    def llm(p, **k):
        aufrufe.append((p, k))
        if k.get("denken"):
            return antwort(denk_antwort)
        if "Du rechnest eine Aufgabe aus der Technik nach" in p:
            return rb_bestaetigung if "Schreibweise (wichtig" in p else RB_1399
        return antwort(WIEDER_1401)
    rpl.frage_llm = llm
    rpl.RECHEN_PRUEFUNG_VERSION = version
    st = rpl.rechnung_pruefen(PROMPT, {"status": "BEANTWORTET", "loesung": ERSTE, "hinweis": "h"}, FRAGE, [CHUNK])
    return st, aufrufe
alt = rpl.frage_llm, rpl.SCAFFOLDING_VERSION, rpl.RECHEN_PRUEFUNG_VERSION
try:
    rpl.SCAFFOLDING_VERSION = "G-v5"
    st, auf = lauf("RP-v8", DENK)
    check("V13.3 RP-v8 reproduziert Log 18:02 (nachgebessert mit 1401)", st["rechen_pruefung"] == "nachgebessert" and "1401" in st["loesung"])
    check("V13.3 RP-v8 ruft keinen Denkmodus", not any(k.get("denken") for _, k in auf))
    st, auf = lauf("RP-v9", DENK)
    check("V13.3 RP-v9: 1401 nicht mehr angenommen, Denkmodus liefert 1431", st["rechen_pruefung"] == "denkmodus" and "1431" in st["loesung"] and "1401" not in st["loesung"].split(".")[0])
    check("V13.3 RP-v9: genau ein Denkmodus-Aufruf, Log-Vermerk", sum(1 for _, k in auf if k.get("denken")) == 1 and "Denkmodus: angenommen" in st["rechen_befund"])
    st, auf = lauf("RP-v9", WIEDER_1401)
    check("V13.3 RP-v9: Denkmodus wieder übernommen -> verworfen, bleibt markiert", st["rechen_pruefung"] == "markiert" and "Denkmodus: verworfen" in st["rechen_befund"])
    st, auf = lauf("RP-v9", "Die Drehzahl beträgt 1431 min⁻¹. Begründung: n = 1500 · (1 - 0,046) = 1450 min⁻¹.")
    check("V13.3 RP-v9: Denkmodus mit Rechenfehler -> verworfen", st["rechen_pruefung"] == "markiert" and "Denkmodus: verworfen" in st["rechen_befund"])
    # keine Rechenfrage: kein Denkmodus
    rpl.RECHEN_PRUEFUNG_VERSION = "RP-v9"
    st2 = {"status": "BEANTWORTET", "loesung": "x", "hinweis": "h", "rechen_pruefung": "markiert", "rechen_befund": ""}
    rpl._denk_wiederholung(PROMPT, st2, "Was ist Remanenz?", [CHUNK], lambda t: [])
    check("V13.3 keine Rechenfrage: Denkmodus übersprungen", st2["rechen_pruefung"] == "markiert" and "Denkmodus" not in st2["rechen_befund"])
finally:
    rpl.frage_llm, rpl.SCAFFOLDING_VERSION, rpl.RECHEN_PRUEFUNG_VERSION = alt

# --- 3b. V13.3.1: Rechenfrage ohne jede Prüfung (Pumpenmotor, App-Test 18:38)
FP = ("Ein Pumpenmotor mit Käfigläufer hat den Kippschlupf sK = 0,15. Um das Stillstandsmoment zu erhöhen, wird der "
      "Läuferwiderstand Rr durch Abdrehen der Kurzschlussringe um 25 % vergrößert. Um welchen Faktor MstR/Mst steigt das Stillstandsmoment?")
AP = ("Das Verhältnis M_stR / M_st beträgt 1,25.\nBegründung: Der Läuferwiderstand R_r wird um 25 % vergrößert, was dem Faktor 1,25 "
      "entspricht. Nach dem Rechenweg aus Aufgabe 4.10 ergibt sich für das neue Stillstandsmoment M_stR = 1,25 · M_st.")
DP = ("Das Stillstandsmoment steigt um den Faktor 1,235.\nBegründung: Nach Gl. 4.45 wird sK2 = 1,25 · 0,15 = 0,1875. Mit s = 1 gilt "
      "nach Gl. 4.41 Mst = 2 MK/(sK + 1/sK): vorher 0,15 + 1/0,15 = 6,817, nachher 0,1875 + 1/0,1875 = 5,521. "
      "Verhältnis: 6,817 / 5,521 = 1,235.")
CP = {"id": "fischer_pdf_0948", "thema": "4.3", "score": 0.6, "text": "Aufgabe 4.10 ... Ergebnis: MstR/Mst = 1,18. Mst = 2 MK/(sK/1 + 1/sK)"}
def lauf_p(version, denk, loesung=AP):
    aufrufe = []
    def llm(p, **k):
        aufrufe.append((p, k))
        if k.get("denken"):
            return antwort(denk)
        if "Du rechnest eine Aufgabe aus der Technik nach" in p:
            return "kaputt"
        return antwort(loesung)
    rpl.frage_llm = llm
    rpl.RECHEN_PRUEFUNG_VERSION = version
    pr = "…\n### Frage\n" + FP + "\n\nAntworte genau …"
    return rpl.rechnung_pruefen(pr, {"status": "BEANTWORTET", "loesung": loesung, "hinweis": "h"}, FP, [CP]), aufrufe
try:
    rpl.SCAFFOLDING_VERSION = "G-v5"
    st, auf = lauf_p("RP-v8", DP)
    check("V13.3.1 RP-v8 reproduziert: ok ohne Prüfung", st["rechen_pruefung"] == "ok" and not any(k.get("denken") for _, k in auf))
    st, auf = lauf_p("RP-v9", DP)
    check("V13.3.1 RP-v9: ungeprüfte Rechenantwort -> Denkmodus 1,235", st["rechen_pruefung"] == "denkmodus" and "1,235" in st["loesung"])
    st, auf = lauf_p("RP-v9", AP)
    check("V13.3.1 RP-v9: Denkmodus ohne Rechnung verworfen -> ungeprueft", st["rechen_pruefung"] == "ungeprueft" and "Denkmodus: verworfen" in st["rechen_befund"])
    st, auf = lauf_p("RP-v9", DP, loesung=DP)
    check("V13.3.1 RP-v9: Antwort mit eigener Rechnung bleibt ok, kein Denkmodus", st["rechen_pruefung"] == "ok" and not any(k.get("denken") for _, k in auf))
finally:
    rpl.frage_llm, rpl.SCAFFOLDING_VERSION, rpl.RECHEN_PRUEFUNG_VERSION = alt

# --- 4. Kontextfenster in frage_llm (ohne Netz: requests.post ersetzt)
class R:
    def __init__(self): self.payload = None
    def raise_for_status(self): pass
    def json(self): return {"response": "ok"}
gesendet = []
def post(url, json=None, timeout=None):
    gesendet.append((json, timeout)); return R()
alt_post, alt_ctx = rpl.requests.post, rpl.KONTEXT_TOKENS
try:
    rpl.requests.post = post
    rpl.KONTEXT_TOKENS = None
    rpl.frage_llm("x", options={"temperature": 0})
    check("V13.3 ohne LERNASSISTENT_CTX: kein num_ctx (unverändert)", "num_ctx" not in gesendet[-1][0]["options"] and gesendet[-1][0]["think"] is False)
    rpl.KONTEXT_TOKENS = 8192
    rpl.frage_llm("x", options={"temperature": 0})
    check("V13.3 mit LERNASSISTENT_CTX=8192: num_ctx 8192", gesendet[-1][0]["options"]["num_ctx"] == 8192)
    rpl.frage_llm("x")
    check("V13.3 num_ctx auch ohne options", gesendet[-1][0]["options"]["num_ctx"] == 8192)
    rpl.frage_llm("x", options={"temperature": 0}, denken=True)
    check("V13.3 Denkmodus: think True, num_ctx 16384, Timeout 900 s", gesendet[-1][0]["think"] is True and gesendet[-1][0]["options"]["num_ctx"] == 16384 and gesendet[-1][1] == 900)
    check("V13.3.1 normale Zeitgrenze 300 s", gesendet[-2][1] == 300)
    n = [0]
    def post_timeout(url, json=None, timeout=None):
        n[0] += 1
        if n[0] == 1:
            raise rpl.requests.exceptions.ReadTimeout("simuliert")
        return R()
    rpl.requests.post = post_timeout
    check("V13.3.1 ein Wiederholungsversuch nach Zeitüberschreitung", rpl.frage_llm("x") == "ok" and n[0] == 2)
    def post_immer(url, json=None, timeout=None):
        raise rpl.requests.exceptions.ReadTimeout("simuliert")
    rpl.requests.post = post_immer
    try:
        rpl.frage_llm("x"); geworfen = False
    except rpl.requests.exceptions.ReadTimeout:
        geworfen = True
    check("V13.3.1 nach zwei Zeitüberschreitungen Fehler nach außen", geworfen)
finally:
    rpl.requests.post, rpl.KONTEXT_TOKENS = alt_post, alt_ctx

# --- 5. App-Chip
app = open(next(p for p in (_pl.Path("app.py"), _pl.Path("lernassistent/app.py")) if p.exists()), encoding="utf-8").read()
check("V13.3 App: Chip für Denkmodus", 'rp == "denkmodus"' in app)
check("V13.3.1 App: Fehler statt Abbruch, Köpfe für denkmodus/ungeprueft", "st.stop()" in app and 'markiert == "denkmodus"' in app and 'rp == "ungeprueft"' in app)

print(f"\n{ok} bestanden, {fail} fehlgeschlagen")
_sys.exit(1 if fail else 0)

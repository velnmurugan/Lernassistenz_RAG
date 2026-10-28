"""Offline-Test V13.5 (RP-v11, RB-v6). Ohne Ollama. Grundlage: echte Rohtexte und Antworten aus dem RV-Lauf V134 (27 Oct 2026,
daten_v135_rv_v134.json) und N100-Antworten ohne RAG. Start (aus ~/RAG): python skripte/evaluation/teste_v135_offline.py"""
import sys as _sys, pathlib as _pl, json
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import rag_pipeline as rpl
import rechenpruefung as rp
import rechenbaustein as rb

ok = fail = 0
def check(name, cond):
    global ok, fail
    ok += bool(cond); fail += (not cond)
    print(("PASS " if cond else "FAIL ") + name)

D = json.loads((_pl.Path(__file__).parent / "daten_v135_rv_v134.json").read_text(encoding="utf-8"))
MAT = "235 225 1000"

# --- 1. RB-v6 auf den echten Rohtexten (V134: nur 14 von 26 auswertbar)
def rb6(nr, i):
    return rb.rechne_v6(rb.parse_v6(D[nr]["rb"][i]), D[nr]["frage"], MAT)
def nah(res, soll, rel=0.006):
    return any(abs(w - soll) <= rel * abs(soll) for _, w in res.get("ergebnisse", []))
check("V13.5 R02 Einheiten in RECHNUNG ('1,5 mm + 2 * 0,25 mm') auswertbar", bool(rb6("R02", 0).get("ergebnisse")))
check("V13.5 R02 Retry mit ' / '-Trennern auswertbar", bool(rb6("R02", 1).get("ergebnisse")))
check("V13.5 R04 Rechnung nur unter WERTE -> M = 1,783", nah(rb6("R04", 0), 1.7825))
check("V13.5 R17 Rechnung nur unter WERTE auswertbar", bool(rb6("R17", 0).get("ergebnisse")))
check("V13.5 R18 Umformungsschritte übersprungen -> R_V = 0,8", nah(rb6("R18", 0), 0.8))
check("V13.5 R19 '-> Korrektur:' gelesen", bool(rb6("R19", 0).get("ergebnisse")))
check("V13.5 R20 Komma-getrennte Zeile + 'M_K = M_K' -> Faktor 1,2347", nah(rb6("R20", 0), 1.2347))
check("V13.5 R22 Komma-getrennt: 97,92 % / 98,50 % / 105,4 kW", nah(rb6("R22", 1), 0.9792) and nah(rb6("R22", 1), 0.985) and nah(rb6("R22", 1), 105.41))
check("V13.5 R22 nur WERTE mit Rechenausdruck -> P_2_opt 105,4", nah(rb6("R22", 0), 105.41))
check("V13.5 R01 Reihenfolge (P_ab2 erst später definiert) -> ΔP 78,95 MW", nah(rb6("R01", 0), 78.947e6))
alle = [(nr, i) for nr in D for i in range(len(D[nr]["rb"]))]
n6 = sum(bool(rb6(nr, i).get("ergebnisse")) for nr, i in alle)
n5 = sum(bool(rb.rechne_v5(rb.parse_v5(D[nr]["rb"][i]), D[nr]["frage"], MAT).get("ergebnisse")) for nr, i in alle)
print(f"     auswertbare Rohtexte: RB-v5 {n5}, RB-v6 {n6} von {len(alle)}")
check("V13.5 RB-v6 wertet mindestens 23 der 26 Rohtexte aus (RB-v5: 14)", n6 >= 23 and n5 <= 15)
for nr, i in alle:  # was RB-v5 schon konnte, bleibt gleich
    r5 = rb.rechne_v5(rb.parse_v5(D[nr]["rb"][i]), D[nr]["frage"], MAT)
    if r5.get("ergebnisse"):
        r6 = rb6(nr, i)
        if [n for n, _ in r5["ergebnisse"]] == [n for n, _ in r6.get("ergebnisse", [])] and not all(
                nah(r6, w, 1e-9) for _, w in r5["ergebnisse"]):
            check(f"V13.5 {nr}/{i} RB-v6 = RB-v5", False)
check("V13.5 Kettenzeile 'x = b / c = 5' bleibt eine Zeile", rb.parse_v6("WERTE:\nb = 10\nc = 2\nRECHNUNG:\nx = b / c = 5\nERGEBNIS: x")["schritte"] == [("x", "b / c")])
check("V13.5 Name wie Einheit bleibt ('2 * s' mit s als Größe)", rb._ohne_einheiten_v6("1500 * (1 - s)", {"s"}) == "1500 * (1 - s)")
# F15: wiederholte Zahl einer berechneten Größe nicht mehr in der Anzeige
F15 = ("FORMEL: n = U_q / (0,7 * 2 * N * B * l * d * pi)\nWERTE:\nU_q = 400 V\nN = 50\nB = 0,8 T\nl = 0,4 m\nd = 0,3 m\nRECHNUNG:\n"
       "n = U_q / (0,7 * 2 * N * B * l * d * pi)\nn = 19,298\nERGEBNIS: n\nEINHEIT: s^-1\nQUELLE: GRUNDWISSEN")
r = rb.rechne_v6(rb.parse_v6(F15), "50 Windungen 0,8 T 70 % d = 0,3 m l = 0,4 m 400 V", "")
check("V13.5 F15: Anzeige ohne 'n = 19,298'", "19,298" not in rb.pruefloesung(r) and nah(r, 18.95, 0.001))

# --- 2. RP-v11: LaTeX-Hochzahlen, Brüche mit Einheiten, Denkantworten aus V134
def befunde(t, f, v):
    return [b["text"] for b in rp.pruefe(t, f, v)]
check("V13.5 R04 Denkantwort (1783 Nmm, 'min^{-1}'): v10 Befund, v11 keiner", befunde(D["R04"]["denk"], D["R04"]["frage"], "RP-v10")
      and not befunde(D["R04"]["denk"], D["R04"]["frage"], "RP-v11"))
check("V13.5 R21 Denkantwort (2833): v11 keiner, prüfbare Rechnung", not befunde(D["R21"]["denk"], D["R21"]["frage"], "RP-v11"))
A55 = r"Eingesetzt ergibt dies $s = \frac{1500\,\text{min}^{-1} - (-750)\,\text{min}^{-1}}{1500\,\text{min}^{-1}} = \frac{2250}{1500} = 1,5$."
check("V13.5 N100 F55 (ohne RAG): Bruch mit Einheiten kein Fehlbefund", befunde(A55, "", "RP-v10") and not befunde(A55, "", "RP-v11"))
b, _ = rp.bereinige_ueberlegung_v11(D["R01"]["orig"])
check("V13.5 R01: '(Hinweis: Hier liegt ein Widerspruch … Ich muss …' abgeschnitten, Rechnung bleibt",
      "Widerspruch" not in b and "78,95 MW" in b and b.rstrip().endswith("."))
with rp.modus("RP-v11"):
    check("V13.5 R01: Endergebnis 78,95 (vorher 900)", rp._endergebnis(b)[0] == 78.95)
# Übernahme nur bei geänderten Zahlen
check("V13.5 Faktenfrage mit Buchzahlen (B30-Muster): kein Übernahme-Befund", not rp.pruefe_uebernahme(
    "Es entstehen 3,4 Fehler pro Million.", "Wie viele Fehler entstehen bei 6 Sigma mit 1,5 Sigma Schwankung?",
    "Bei 6 Sigma und 1,5 Sigma Verschiebung entstehen 3,4 ppm Fehler.", "RP-v11"))
check("V13.5 dieselbe Antwort, Frage mit anderen Zahlen: Befund bleibt", rp.pruefe_uebernahme(
    "Es entstehen 3,4 Fehler pro Million.", "Wie viele Fehler entstehen bei 5 Sigma mit 1,2 Sigma Schwankung?",
    "Bei 6 Sigma und 1,5 Sigma Verschiebung entstehen 3,4 ppm Fehler.", "RP-v11"))

# --- 3. Ablauf: Denkmodus R20 (1,23 richtig, letzte Rechnung Zwischenwert) mit bestätigender Nachrechnung
def antwort(l): return "STATUS: BEANTWORTET\nLÖSUNG: " + l + "\nÜBERLEGUNG: x\nHINWEIS: h"
ERSTE = 'Der Läuferwiderstand Rr wird um 25 % vergrößert, was dem Faktor 1,25 entspricht. Nach Gl. 4.45 ergibt sich der neue Kippschlupf s_K2 = 1,25 · 0,15 = 0,1875. Für das alte Stillstandsmoment gilt M_st = 2 M_K / (0,15 + 1/0,15) = 0,385 M_K. Für das neue Stillstandsmoment gilt M_stR = 2 M_K / (0,1875 + 1/0,1875) = 0,469 M_K. Das Verhältnis der Momente ist M_stR / M_st = 0,469 M_K / 0,385 M_K = 1,22.'  # echte erste Antwort V134 R20
DENK20 = ("Der Faktor M_stR/M_st beträgt ca. 1,23. Begründung: Nach Gl. 4.45 steigt der Kippschlupf auf s_KR = 1,25 · 0,15 = 0,1875. "
          "Das Verhältnis ergibt sich aus dem Quotienten der Nenner: (0,15 + 1/0,15) / (0,1875 + 1/0,1875).")
def lauf(version, zweite="kaputt"):
    auf = []
    def llm(p, **k):
        auf.append(k)
        if k.get("denken"):
            return antwort(DENK20)
        if "Du rechnest eine Aufgabe aus der Technik nach" in p:
            return zweite if "Schreibweise (wichtig" in p else D["R20"]["rb"][0]
        return antwort(ERSTE)
    rpl.frage_llm = llm
    rpl.RECHEN_PRUEFUNG_VERSION = version
    return rpl.rechnung_pruefen("…\n### Frage\n" + D["R20"]["frage"] + "\n\nAntworte …", {"status": "BEANTWORTET", "loesung": ERSTE, "hinweis": "h"},
                                D["R20"]["frage"], [{"id": "c", "thema": "t", "score": 0.6, "text": "M_st = 2 M_K/(s_K + 1/s_K) Gl. 4.41"}])
alt = rpl.frage_llm, rpl.SCAFFOLDING_VERSION, rpl.RECHEN_PRUEFUNG_VERSION
try:
    rpl.SCAFFOLDING_VERSION = "G-v5"
    st = lauf("RP-v10")
    check("V13.5 R20 RP-v10 reproduziert: nicht 1,23", "1,23" not in st["loesung"].split(".")[0] + st["loesung"][:40] or st["rechen_pruefung"] != "denkmodus")
    st = lauf("RP-v11")
    check("V13.5 R20 RP-v11, Bestätigung scheitert: Denkmodus 1,23 angenommen (Nachrechnung 1,2347)",
          st["rechen_pruefung"] == "denkmodus" and "1,23" in st["loesung"][:60])
    st = lauf("RP-v11", zweite=D["R20"]["rb"][0])
    check("V13.5 R20 RP-v11, Bestätigung gelingt: ersetzt mit 1,235", st["rechen_pruefung"] == "ersetzt" and "1,235" in st["loesung"][:60])
finally:
    rpl.frage_llm, rpl.SCAFFOLDING_VERSION, rpl.RECHEN_PRUEFUNG_VERSION = alt

print(f"\n{ok} bestanden, {fail} fehlgeschlagen")
_sys.exit(1 if fail else 0)

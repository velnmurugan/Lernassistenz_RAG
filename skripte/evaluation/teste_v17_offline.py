"""Offline-Test V17b (RP-v13 = RP-v12 + Vergleich in Grundeinheiten; RB-v8 = RB-v7 + Dimensionsprüfung + zwei Lesekorrekturen) mit
echten Antworten und Nachrechnungen aus den Läufen V135/V15/V16 (RV-v2 R09, R11, R17; N100 F1, F14; RV-v1 R09, R13). Ohne Ollama.
Start (aus ~/RAG): python skripte/evaluation/teste_v17_offline.py"""
import sys as _sys, pathlib as _pl, json
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import rag_pipeline as rpl
import rechenbaustein as rb
import dimensionspruefung as dp

ok = fail = 0


def check(name, cond):
    global ok, fail
    ok += bool(cond); fail += (not cond)
    print(("PASS " if cond else "FAIL ") + name)


D = json.load(open(_pl.Path(__file__).with_name("daten_v17.json"), encoding="utf-8"))
CH = [{"id": "c", "thema": "t", "score": 0.6, "text": "Der induktive Blindwiderstand X_L = ω L. Kreisfrequenz ω = 2 π f."}]


def antwort(l, status="BEANTWORTET"):
    return f"STATUS: {status}\nLÖSUNG: " + l + "\nÜBERLEGUNG: x\nHINWEIS: h"


def lauf(fall, v13, rb_folge, rb_version="RB-v8", status="BEANTWORTET"):
    """rb_folge: Antworten auf Nachrechnungs-Prompts der Reihe nach (erste, Bestätigung, Retry, dritte …)."""
    folge, auf = list(rb_folge), []

    def llm(p, **k):
        if "Du rechnest eine Aufgabe aus der Technik nach" in p:
            auf.append(("rb", (k.get("options") or {}).get("temperature")))
            return folge.pop(0) if folge else "kaputt"
        auf.append(("text", None))
        return antwort(D[fall]["erste"], status)
    rpl.frage_llm = llm
    rpl.RP_V12, rpl.RP_V13, rpl.NACHRECHNUNG_VERSION = True, v13, rb_version
    q = D[fall]["frage"]
    st = rpl.rechnung_pruefen("…\n### Frage\n" + q + "\n\nAntworte …", {"status": status, "loesung": D[fall]["erste"], "hinweis": "h"},
                              q, CH)
    return st, auf


alt = (rpl.frage_llm, rpl.SCAFFOLDING_VERSION, rpl.RECHEN_PRUEFUNG_VERSION, rpl.NACHRECHNUNG_VERSION, rpl.RP_V12, rpl.RP_V13)
try:
    rpl.SCAFFOLDING_VERSION, rpl.RECHEN_PRUEFUNG_VERSION = "G-v5", "RP-v11"
    # 1. RB-v8 Lesekorrekturen (R11: zweite Nachrechnung "pi = pi", "L = 20/1000 H")
    r11_zweit, frage11 = D["R11"]["rb"][1], D["R11"]["frage"]
    rb.RB_V8 = False
    a = rb.rechne_v7(rb.parse_v7(r11_zweit), frage11, "")
    rb.RB_V8 = True
    b = rb.rechne_v7(rb.parse_v7(r11_zweit), frage11, "")
    check("V17 RB-v7 liest R11 zweite Nachrechnung falsch (125000 Hz)", abs(a["ergebnisse"][0][1] - 125000) < 1)
    check("V17 RB-v8: R11 zweite Nachrechnung 39,79 Hz", abs(b["ergebnisse"][0][1] - 39.789) < 0.01)
    c = rb.rechne_v7(rb.parse_v7(D["R11"]["rb"][0]), frage11, "")
    check("V17 RB-v8: R11 erste Nachrechnung unverändert 39,79 Hz", abs(c["ergebnisse"][0][1] - 39.789) < 0.01)
    rb.RB_V8 = False

    # 2. Vergleich in Grundeinheiten ohne Faktor 10³ (F1: 4,8e17 gegen 4,8e-19 galt als bestätigt)
    e1 = {"ergebnisse": [("n", 4.8e17)], "einheit": "1"}
    e2 = {"ergebnisse": [("n", 4.8e-19)], "einheit": "1"}
    check("V17 F1: 4,8e17 und 4,8e-19 stimmen nicht überein", not rpl._gleiche_ergebnisse(e1, e2))
    check("V17 gleiche Größe, andere Vorsilbe: 20 mA = 0,02 A",
          rpl._gleiche_ergebnisse({"ergebnisse": [("I", 20.0)], "einheit": "mA"}, {"ergebnisse": [("I", 0.02)], "einheit": "A"}))
    check("V17 ohne Einheit: Verhalten wie bisher (_passt)",
          rpl._gleiche_ergebnisse({"ergebnisse": [("x", 5.0)], "einheit": ""}, {"ergebnisse": [("x", 5.01)], "einheit": ""}))
    check("V17 leere Nachrechnung: keine Übereinstimmung", not rpl._gleiche_ergebnisse(e1, {}))

    # 3. Dimensionsprüfung (DP-v1) auf echten Nachrechnungen
    v = dp.pruefe(D["R09"]["rb"][0])
    check("V17 DP R09 erste (Gewichtskraft durch g): Widerspruch kg statt N", v["widerspruch"] and "kg" in v["detail"])
    check("V17 DP R09 zweite (richtig 0,01068 m²): kein Widerspruch", not dp.pruefe(D["R09"]["rb"][1])["widerspruch"])
    check("V17 DP RV-v1 R09 (Länge fehlt, Ergebnis m statt m²): Widerspruch", dp.pruefe(D["RV1_R09_rb"])["widerspruch"])
    check("V17 DP F14 (eingesetzte Zahlen 0,5 * 0,5 * 4**2, richtig): kein Widerspruch", not dp.pruefe(D["F14_rb"])["widerspruch"])
    check("V17 DP RV-v1 R13 (Einheit am Ende der RECHNUNG, richtig): kein Widerspruch", not dp.pruefe(D["RV1_R13_rb"])["widerspruch"])
    check("V17 DP R11 beide richtig: kein Widerspruch", not any(dp.pruefe(x)["widerspruch"] for x in D["R11"]["rb"]))
    check("V17 DP F1 zweite (n = Q/e mit e in 1/C): Widerspruch", dp.pruefe(D["F1"]["rb"][1])["widerspruch"])
    check("V17 DP Einheiten: Ω·mm²/m · m / mm² = Ω",
          dp.einheit_dim("Ω·mm²/m") is not None and dp._mal(dp._mal(dp.einheit_dim("Ω·mm²/m"), dp.einheit_dim("m")),
                                                          dp.einheit_dim("mm²"), -1) == dp.einheit_dim("Ω"))
    check("V17 DP Einheiten: VA = W, Nm = J, 1/min = Hz, kWh = J",
          dp.einheit_dim("VA") == dp.einheit_dim("W") and dp.einheit_dim("Nm") == dp.einheit_dim("J")
          and dp.einheit_dim("1/min") == dp.einheit_dim("Hz") and dp.einheit_dim("kWh") == dp.einheit_dim("J"))
    check("V17 DP Summe verschiedener Dimensionen: Widerspruch",
          dp.pruefe("FORMEL: x\nWERTE:\nU = 230 V\nI = 2 A\nRECHNUNG:\nx = U + I\nERGEBNIS: x\nEINHEIT: V\nQUELLE: x")["widerspruch"])
    check("V17 DP nicht lesbar: kein Widerspruch", not dp.pruefe("kaputt")["widerspruch"])

    # 4. Pipeline R09 mit RB-v8: erste Nachrechnung verworfen (Dimension), Retry mit Befund, Bestätigung -> ersetzt mit 0,01068 m²
    st, auf = lauf("R09", True, [D["R09"]["rb"][0], D["R09"]["rb"][1], D["R09"]["rb"][1]], status="TEILWEISE")
    check("V17 R09 RB-v8: Retry nach Dimensionsbefund", "Retry (RB-v3) nach dimension" in st["rechen_befund"])
    check("V17 R09 RB-v8: ersetzt mit 0,01068 m²", st["rechen_pruefung"] == "ersetzt" and "0,01068" in st["loesung"][:200])
    st, auf = lauf("R09", False, [D["R09"]["rb"][0], D["R09"]["rb"][1]], rb_version="RB-v7", status="TEILWEISE")
    check("V17 R09 ohne Änderungen: nicht ersetzt (V16)", st["rechen_pruefung"] != "ersetzt")
    # 4b. R11 mit RB-v8: Bestätigung gelingt (Lesekorrektur) -> ersetzt mit 39,79 Hz
    st, auf = lauf("R11", True, D["R11"]["rb"])
    check("V17 R11 RB-v8: bestätigt und ersetzt (39,79 Hz)", st["rechen_pruefung"] == "ersetzt" and "39,79" in st["loesung"][:150])
    st, auf = lauf("R11", False, D["R11"]["rb"], rb_version="RB-v7")
    check("V17 R11 ohne Änderungen: abweichung_ungestuetzt (V16)", st["rechen_pruefung"] == "abweichung_ungestuetzt")

    # 5. R17: Kopfsatz angeglichen (942 N), bestätigte Nachrechnung 1346 N ohne Buchformel -> ersetzt mit Vermerk
    st, auf = lauf("R17", True, [D["R17"]["rb"][0], D["R17"]["rb"][0]])
    check("V17 R17: ersetzt mit 1346 N", st["rechen_pruefung"] == "ersetzt" and "1346" in st["loesung"][:200].replace(".", ""))
    st, auf = lauf("R17", False, [D["R17"]["rb"][0], D["R17"]["rb"][0]], rb_version="RB-v7")
    check("V17 R17 ohne RP-v13: kopf_korrigiert (V16)", st["rechen_pruefung"] == "kopf_korrigiert")

    # 6. F1: zweite Nachrechnung dimensionsfalsch, Retry unlesbar -> keine Bestätigung, Antwort bleibt
    st, auf = lauf("F1", True, D["F1"]["rb"] + ["kaputt"])
    check("V17 F1: keine falsche Bestätigung, Antwort 18,75 · 10^18 bleibt", "Bestätigung: ja" not in st["rechen_befund"]
          and "18,75" in st["loesung"][:120])

    # 7. Schalter
    import importlib, os
    os.environ["LERNASSISTENT_RP"] = "RP-v13"
    m = importlib.reload(rpl)
    check("V17 Schalter: RP-v13 -> intern RP-v11 + RP_V12 + RP_V13",
          m.RP_V13 is True and m.RP_V12 is True and m.RECHEN_PRUEFUNG_VERSION == "RP-v11")
    os.environ["LERNASSISTENT_RB"] = "RB-v8"
    m = importlib.reload(rpl)
    check("V17 Schalter: RB-v8 -> parse_v7 + Dimensionsprüfung, RB_V8", m._rb_leser() == (rb.parse_v7, m._rechne_mit_dimension) and rb.RB_V8 is True)
    os.environ["LERNASSISTENT_RP"], os.environ["LERNASSISTENT_RB"] = "RP-v12", "RB-v7"
    m = importlib.reload(rpl)
    check("V17 RP-v12 + RB-v7: ohne Änderungen", m.RP_V13 is False and m.RP_V12 is True
          and m._rb_leser() == (rb.parse_v7, rb.rechne_v7) and rb.RB_V8 is False)
    os.environ.pop("LERNASSISTENT_RP"); os.environ.pop("LERNASSISTENT_RB")
    rpl = importlib.reload(rpl)
finally:
    rb.RB_V8 = False
print(f"\n{ok} bestanden, {fail} fehlgeschlagen")
_sys.exit(1 if fail else 0)

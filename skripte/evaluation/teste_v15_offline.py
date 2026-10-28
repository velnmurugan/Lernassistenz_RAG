"""Offline-Test V15 (RB-v7: Einheiten in Grundeinheiten umrechnen). Echte Rohtexte der Nachrechnung aus V134 und V14C/V14D.
Start (aus ~/RAG): python skripte/evaluation/teste_v15_offline.py"""
import sys as _sys, pathlib as _pl, json
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import rechenbaustein as rb
import rag_pipeline as rpl

ok = fail = 0
def check(name, cond):
    global ok, fail
    ok += bool(cond); fail += (not cond)
    print(("PASS " if cond else "FAIL ") + name)

nah = lambda a, b, t=0.005: abs(a - b) <= t * abs(b)
f = rb.einheit_faktor_v7
check("V15 Faktoren: mm, kW, h, %, Nmm", nah(f("mm"), 1e-3) and nah(f("kW"), 1e3) and nah(f("h"), 3600) and nah(f("%"), 0.01) and nah(f("Nmm"), 1e-3))
check("V15 Faktoren: zusammengesetzt Ω·mm²/m, €/kWh, min⁻¹, 1/min, U/min", nah(f("Ω·mm²/m"), 1e-6) and nah(f("€/kWh"), 1 / 3.6e6)
      and nah(f("min⁻¹"), 1 / 60) and nah(f("1/min"), 1 / 60) and nah(f("U/min"), 1 / 60))
check("V15 Faktoren: Grundeinheiten 1, °C/Grad nicht umrechnen", f("Ω") == 1 and f("kg·m²") == 1 and f("m/s") == 1 and f("°C") is None and f("°") is None)
check("V15 Faktoren: Mio €", nah(f("Mio €"), 1e6))

D = json.load(open(_pl.Path(__file__).with_name("daten_v15_rb.json"), encoding="utf-8"))
def r7(k):
    return rb.rechne_v7(rb.parse_v7(D[k]["rb"]), D[k]["frage"], "")
def r6(k):
    return rb.rechne_v6(rb.parse_v6(D[k]["rb"]), D[k]["frage"], "")
e = dict(r7("R01")["ergebnisse"])
check("V15 R01: Einsparung 31,58 Mio € (RB-v6: 3,16·10¹⁰ wegen €/kWh · Wh)", nah(e["K_einsparung"], 31.5789e6) and nah(e["delta_P"], 78.947e6))
for k in ("R02a", "R02b", "R02c"):
    x = r7(k)
    check(f"V15 {k}: R = 3,12 Ω (RB-v6: 3120, Längen in mm)", x.get("si") == "ja" and nah(x["ergebnis"], 3.12) and nah(r6(k)["ergebnis"], 3120))
x = r7("R22")
check("V15 R22: Ergebnis zurück in kW, Einheit nach Namen zugeordnet (105,4 kW)", nah(dict(x["ergebnisse"])["P_2_opt"], 105.41))
check("V15 R21: Zahl ohne Einheit wiederholt -> gleicher Faktor, Ergebnis wie RB-v6", nah(r7("R21")["ergebnis"], r6("R21")["ergebnis"]))
x = r7("R04")
check("V15 R04: Zahlenwertgleichung (60 in der Rechnung) -> keine Umrechnung, Einheiten nur gestrichen (1,7825; RB-v6 1,7845 wegen „min^-1“)",
      x.get("si") != "ja" and nah(x.get("ergebnis"), 1.78254, 0.001) and not nah(r6("R04").get("ergebnis"), 1.78254, 0.001))
x = r7("R09")
check("V15 R09: Einheit „Vs/(Am)“ lesbar (RB-v6: wert_unlesbar) -> A = 0,01731 m² = 173 cm²", r6("R09")["grund"] == "wert_unlesbar"
      and nah(x["ergebnis"], 0.017308))
x = r7("R04b")
check("V15 R04b: „70/100“, „900/60“ rechnet das Modell selbst um -> nicht doppelt; Ergebnis in Nmm (1782,5)", nah(x["ergebnis"], 1782.5))
check("V15 Faktoren: zusammengeschrieben Vs/(Am), kgm²", f("Vs/(Am)") == 1 and f("kgm²") == 1)
check("V15 F15: „n = 19.298 s^-1“ wird nicht als 19,298 s − 1 gerechnet -> 18,95 1/s (RB-v6 18,3)", nah(r7("F15")["ergebnis"], 18.947)
      and nah(r6("F15")["ergebnis"], 18.298))
check("V15 F7: „J/(°C*kg)“ lesbar (RB-v6: wert_unlesbar)", r6("F7")["grund"] == "wert_unlesbar" and r7("F7").get("ergebnisse"))
check("V15 Belegprüfung bleibt: erfundene Zahl -> erfunden", rb.rechne_v7(rb.parse_v7(
    "FORMEL: R = U / I\nWERTE: U = 230 V; I = 7 mA; k = 17,3\nRECHNUNG: R = U / I * k\nERGEBNIS: R\nEINHEIT: Ω"), "Spannung U = 230 V, Strom I = 7 mA", "")["grund"] == "erfunden")
x = rb.rechne_v7(rb.parse_v7("FORMEL: R = U / I\nWERTE: U = 230 V; I = 7 mA\nRECHNUNG: R = U / I\nERGEBNIS: R\nEINHEIT: kΩ"),
                 "Spannung U = 230 V, Strom I = 7 mA. Widerstand?", "")
check("V15 einfache Vorsilbe: 230 V / 7 mA = 32,86 kΩ", x.get("si") == "ja" and nah(x["ergebnis"], 32.857))
p = rb.parse_v7("FORMEL: x\nRECHNUNG: KEINE\nERGEBNIS: -")
check("V15 RECHNUNG: KEINE bleibt", rb.rechne_v7(p, "", "")["grund"] == "keine_rechnung")
alt = rpl.NACHRECHNUNG_VERSION, rpl.RECHEN_PRUEFUNG_VERSION
try:
    rpl.RECHEN_PRUEFUNG_VERSION, rpl.NACHRECHNUNG_VERSION = "RP-v11", "RB-v7"
    check("V15 Schalter: RP-v11 + LERNASSISTENT_RB=RB-v7 -> parse_v7/rechne_v7", rpl._rb_leser() == (rb.parse_v7, rb.rechne_v7))
    rpl.NACHRECHNUNG_VERSION = ""
    check("V15 Standard: RP-v11 ohne Schalter -> RB-v6", rpl._rb_leser() == (rb.parse_v6, rb.rechne_v6))
finally:
    rpl.NACHRECHNUNG_VERSION, rpl.RECHEN_PRUEFUNG_VERSION = alt
print(f"\n{ok} bestanden, {fail} fehlgeschlagen")
_sys.exit(1 if fail else 0)

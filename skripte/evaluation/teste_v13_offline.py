"""Offline-Test V13 (RP-v6, RB-v3, G-v5). Ohne Ollama. Fälle aus N100 (V11B-Lauf 21 Okt, V12.9-Lauf 24 Okt).
Start (aus ~/RAG): python skripte/evaluation/teste_v13_offline.py"""
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

def nahe(a, b, tol=1e-3):
    return a is not None and abs(a - b) <= tol * abs(b)

# --- 1. Parser (M1)
for ausdruck, soll in [("π/(2√2)*12", 13.3286), ("pi/(2*√2)*12", 13.3286), ("2 π * 1000/60", 104.72), ("2pi*50", 314.16),
                       ("500*(0.5/(2 π*1000/60))²", 0.011399), ("3*6,25*10^18", 1.875e19), ("√3 * 10", 17.3205),
                       ("(1+2)(3+4)", 21.0), ("2 sqrt(2)", 2.8284), ("sqrt3*100", 173.205), ("50**2", 2500.0)]:
    check(f"V13 Parser: {ausdruck}", nahe(rb.sicher_auswerten(ausdruck), soll))
check("V13 Parser: Einheit bleibt Fehler (0,5 m)", rb.sicher_auswerten("0,5 m") is None)
check("V13 Parser: unbekannter Name", rb.sicher_auswerten("x") is None)

# --- 2. Einheitenprodukt in der Prüfung (F62)
F62 = ("Das Ersatzträgheitsmoment beträgt 0,25 kg·m². Die Berechnung erfolgt mit der Formel J_e = m_g (v/ω)². Eingesetzt werden die Masse "
       "m_g = 500 kg, die Geschwindigkeit v = 0,5 m/s und die Winkelgeschwindigkeit ω = 2 π · (1000/60) s⁻¹. Das Ergebnis ist "
       "J_e = 500 · (0,5 / (2 π · 1000/60))² ≈ 0,25 kg·m².")
Q62 = "Eine Last von 500 kg bewegt sich mit 0,5 m/s geradlinig; der Motor dreht mit 1000 1/min. Welches Ersatzträgheitsmoment hat die Last an der Motorwelle?"
for v in ("RP-v5", "RP-v6"):
    b = rp.pruefe(F62, Q62, v)
    check(f"V13 F62 {v}: eigene Rechnung gegen 0,25 erkannt", any("0,0114" in x["text"] for x in b))
check("V13: richtige F62-Lösung bleibt unbeanstandet", not rp.pruefe(F62.replace("0,25", "0,0114"), Q62, "RP-v6"))
check("V13: Einheitenprodukt N·m", not rp.pruefe("Das Moment ist M = 40 N·m · 2 = 80 N·m.", "Moment?", "RP-v6"))

# --- 3. Einheitenwächter (F52)
Q52 = "Ein Drehstromtransformator hat 10 kV Oberspannung und 11,5 A Strangstrom auf der Oberspannungsseite. Welche Scheinleistung hat er?"
b = rp.pruefe("Die Scheinleistung beträgt S_N = √3 · 10 kV · 11,5 A = 200 kW. Begründung: Formel aus dem Lernmaterial.", Q52, "RP-v6")
check("V13 F52: kW bei Scheinleistung gemeldet", any(x.get("art") == "einheit" and "VA" in x["text"] for x in b))
check("V13 F52: RP-v5 meldet es nicht (unverändert)", not any(x.get("art") == "einheit" for x in rp.pruefe("Die Scheinleistung beträgt 200 kW.", Q52, "RP-v5")))
check("V13 F52: kVA ok", not any(x.get("art") == "einheit" for x in rp.pruefe("Die Scheinleistung beträgt 199,2 kVA.", Q52, "RP-v6")))
check("V13 F52: kVA und kW im Satz ok", not any(x.get("art") == "einheit" for x in rp.pruefe("Die Scheinleistung beträgt 200 kVA bei 160 kW Wirkleistung.", Q52, "RP-v6")))
check("V13: zwei Größen in der Frage -> keine Aussage", not rp.pruefe_einheiten("Es sind 200 kW.", "Scheinleistung und Wirkleistung?"))
check("V13: Drehzahl in Hz gemeldet", bool(rp.pruefe_einheiten("Die Welle läuft mit 50 Hz.", "Mit welcher Drehzahl läuft die Welle?")))
check("V13: Drehzahl 3000/min ok", not rp.pruefe_einheiten("Die Welle läuft mit 3000/min.", "Mit welcher Drehzahl läuft die Welle?"))
check("V13: Frage ohne Größe -> leer", not rp.pruefe_einheiten("Es sind 200 kW.", "Wie groß ist der Strom?"))

# --- 4. Bereinigung sichtbarer Überlegung (F29)
F29 = ("Die erforderliche sekundäre Wechselspannung U beträgt 8,5 V. Begründung: U = π/(2√2) · 12 V ≈ 0,637 · 12 V = 7,64 V.\n"
       "*Warte, ich muss strikt L1 und L5 beachten.*\nKorrektur: 13,3 V")
neu, weg = rp.bereinige_ueberlegung(F29)
check("V13 F29: Denktext abgeschnitten", neu.endswith("= 7,64 V.") and weg.startswith("*Warte"))
check("V13: kurzer Text bleibt", rp.bereinige_ueberlegung("Kurz.\n*Warte, doch*")[1] == "")
check("V13: Fachwort Korrekturfaktor bleibt", rp.bereinige_ueberlegung("Der Korrekturfaktor beträgt 1,2 bei Last. Mehr Text hier im Satz.")[1] == "")

# --- 5. Kopfzahlen-Rückfall (F61)
Q61 = "Ein Motor (J0 = 0,02 kgm²) treibt über ein Getriebe eine Welle mit J1 = 1,5 kgm² an, die mit n/10 dreht. Wie groß ist das auf die Motordrehzahl umgerechnete Trägheitsmoment?"
RES61 = {"ergebnisse": [("J", 0.035)], "rechnung": "J = 0.02+1.5*0.01", "formel": "J=J0+J1*(n1/n)^2", "einheit": "kgm²"}
check("V13 F61: Antwort = gegebener Wert -> Befund", bool(rb.vergleiche_v3("Das umgerechnete Trägheitsmoment beträgt 0,02 kgm². Begründung: x", Q61, RES61)))
check("V13 F61: richtige Antwort ohne Befund", not rb.vergleiche_v3("Das umgerechnete Trägheitsmoment beträgt 0,035 kgm². Begründung: x", Q61, RES61))
check("V13: Rückfall nur bei genau einer Zahl mit Einheit", not rb.vergleiche_v3("Bei 230 V und 50 Hz beträgt der Strom 4,3 A.", "Gerät an 230 V, 50 Hz. Strom?", {"ergebnisse": [("I", 4.35)], "rechnung": "", "formel": "", "einheit": "A"}))

# --- 6. Pipeline mit simuliertem Modell
CHUNK = {"id": "c1", "thema": "Ersatzträgheitsmoment", "score": 0.8,
         "text": "Gl. 5.4: Das Ersatzträgheitsmoment einer geradlinig bewegten Masse ist J = m (v/ω)²."}
GUT_RB = ("FORMEL: J = m*(v/w)**2\nWERTE:\nm = 500 kg\nv = 0.5 m/s\nn = 1000/60 1/s\nw = 2*pi*n 1/s\nRECHNUNG:\nJ = m*(v/w)**2\n"
          "ERGEBNIS: J\nEINHEIT: kg*m**2\nQUELLE: Gl. 5.4: J = m (v/ω)²")
SCHLECHT_RB = "FORMEL: J = m*(v/w)**2\nWERTE:\nm = 500 kg\nw = unendlich 1/s\nRECHNUNG:\nJ = m*(v/w)**2\nERGEBNIS: J\nEINHEIT: kg*m**2\nQUELLE: GRUNDWISSEN"
NEU_LOESUNG = "STATUS: BEANTWORTET\nLÖSUNG: Das Ersatzträgheitsmoment beträgt 0,0114 kg·m². Begründung: J = m (v/ω)² mit ω = 104,7 s⁻¹.\nÜBERLEGUNG: x\nHINWEIS: h"
prompt = "…\n### Frage\n" + Q62 + "\n\nAntworte genau …"
alt = rpl.frage_llm, rpl.SCAFFOLDING_VERSION, rpl.RECHEN_PRUEFUNG_VERSION
try:
    rpl.SCAFFOLDING_VERSION, rpl.RECHEN_PRUEFUNG_VERSION = "G-v4", "RP-v6"
    aufrufe = []
    def llm(p, **k):
        aufrufe.append(p)
        if "Du rechnest eine Aufgabe aus der Technik nach" in p:
            return GUT_RB
        return NEU_LOESUNG
    rpl.frage_llm = llm
    st = rpl.rechnung_pruefen(prompt, {"status": "BEANTWORTET", "loesung": F62, "hinweis": "h"}, Q62, [CHUNK])
    check("V13 F62 Ablauf: nachgebessert", st["rechen_pruefung"] == "nachgebessert" and "0,0114" in st["loesung"])
    check("V13 F62 Ablauf: RB-v3 im Log", st["rechen_befund"].count("RB-v3 Ergebnis J") == 1 and "Formel im Material" in st["rechen_befund"])
    check("V13 F62 Ablauf: Original im Log", "0,25" in st["loesung_original"])

    # Retry nach unlesbarem Wert
    folge = iter([SCHLECHT_RB, GUT_RB, NEU_LOESUNG]); aufrufe.clear()
    rpl.frage_llm = lambda p, **k: (aufrufe.append(p), next(folge))[1]
    st = rpl.rechnung_pruefen(prompt, {"status": "BEANTWORTET", "loesung": F62, "hinweis": "h"}, Q62, [CHUNK])
    check("V13 Retry: zweiter RB-Aufruf mit Fehlerbericht", "nicht auswertbar" in aufrufe[1] and "wert_unlesbar" not in aufrufe[1] and "unendlich" in aufrufe[1])
    check("V13 Retry: im Log vermerkt, Lösung korrigiert", "Retry nach wert_unlesbar: ok" in st["rechen_befund"] and st["rechen_pruefung"] == "nachgebessert")

    # RP-v5 unverändert: ein RB-Aufruf mit dem alten Prompt, kein Retry
    rpl.RECHEN_PRUEFUNG_VERSION = "RP-v5"; aufrufe.clear()
    rpl.frage_llm = lambda p, **k: (aufrufe.append(p), GUT_RB if "Du rechnest eine Aufgabe aus der Technik nach" in p else NEU_LOESUNG)[1]
    st = rpl.rechnung_pruefen(prompt, {"status": "BEANTWORTET", "loesung": F62, "hinweis": "h"}, Q62, [CHUNK])
    check("V13 RP-v5 unverändert: RB-v2 im Log", "RB-v2 Ergebnis" in st["rechen_befund"] and "Schreibweise (wichtig" not in aufrufe[0])
    rpl.RECHEN_PRUEFUNG_VERSION = "RP-v6"

    # ungestützte Abweichung (F1-Muster): Nachrechnung ohne Quelle widerspricht einer richtigen Antwort
    Q1 = "Ein Körper trägt eine Ladung von +3 C. Wie viele Elektronen fehlen ihm, wenn 1 C einer Ladung von 6,25·10^18 Elementarladungen entspricht?"
    RB1 = ("FORMEL: n = Q / e\nWERTE:\nQ = 3 C\ne = 6.25*10**18 1/C\nRECHNUNG:\nn = Q/e\nERGEBNIS: n\nEINHEIT: 1\nQUELLE: GRUNDWISSEN")
    L1 = "Es fehlen 1,875·10^19 Elektronen, denn 3 · 6,25·10^18 = 1,875·10^19. Begründung: Mangel an Elektronen."
    aufrufe.clear()
    rpl.frage_llm = lambda p, **k: (aufrufe.append(p), RB1)[1]
    st = rpl.rechnung_pruefen("…\n### Frage\n" + Q1 + "\n\nAntworte genau …", {"status": "BEANTWORTET", "loesung": L1, "hinweis": "h"}, Q1, [CHUNK])
    check("V13 ungestützt: Status", st["rechen_pruefung"] == "abweichung_ungestuetzt")
    check("V13 ungestützt: kein Vermerk, Lösung unverändert, kein Neuschreiben", st["loesung"] == L1 and len(aufrufe) == 1)
    check("V13 ungestützt: Befund im Log", "Nachrechnung" in st["rechen_befund"] and "RB-v3 Ergebnis" in st["rechen_befund"])

    # Bereinigung: Denktext weg, Rechnung ok
    Q = "Wie groß ist der Strom bei 230 V und 46 Ω?"
    L = "Der Strom beträgt 5 A. Begründung: I = U / R = 230 V / 46 Ω = 5 A.\n*Warte, ich muss noch die Regeln beachten.*\nKorrektur: 5 A"
    rpl.frage_llm = lambda p, **k: "FORMEL: I = U/R\nWERTE:\nU = 230 V\nR = 46 Ohm\nRECHNUNG:\nI = U/R\nERGEBNIS: I\nEINHEIT: A\nQUELLE: Gl. 5.4: I = U / R"
    st = rpl.rechnung_pruefen("…\n### Frage\n" + Q + "\n\nAntworte genau …", {"status": "BEANTWORTET", "loesung": L, "hinweis": "h"}, Q, [CHUNK])
    check("V13 Bereinigung: bereinigt, Original im Log", st["rechen_pruefung"] == "bereinigt" and "Warte" in st["loesung_original"] and "Warte" not in st["loesung"])

    # F61-Muster über die Pipeline: Antwort = gegebener Wert -> RB läuft und der Befund greift
    RB61 = ("FORMEL: J = J0 + J1*(n1/n)**2\nWERTE:\nJ0 = 0.02 kgm2\nJ1 = 1.5 kgm2\nv = 1/10\nRECHNUNG:\nJ = J0 + J1*v**2\nERGEBNIS: J\nEINHEIT: kgm²\n"
            "QUELLE: Gl. 5.4: J = J0 + J1 (n1/n)²")
    folge = iter([RB61, "STATUS: BEANTWORTET\nLÖSUNG: Das umgerechnete Trägheitsmoment beträgt 0,035 kgm². Begründung: J = 0,02 + 1,5 · 0,01.\nÜBERLEGUNG: x\nHINWEIS: h"])
    rpl.frage_llm = lambda p, **k: next(folge)
    st = rpl.rechnung_pruefen("…\n### Frage\n" + Q61 + "\n\nAntworte genau …",
                              {"status": "BEANTWORTET", "loesung": "Das umgerechnete Trägheitsmoment beträgt 0,02 kgm². Begründung: Summe.", "hinweis": "h"}, Q61, [CHUNK])
    check("V13 F61 Ablauf: erkannt und korrigiert", st["rechen_pruefung"] == "nachgebessert" and "0,035" in st["loesung"])
finally:
    rpl.frage_llm, rpl.SCAFFOLDING_VERSION, rpl.RECHEN_PRUEFUNG_VERSION = alt

# --- 7. G-v5
chunks = [{"id": "a", "thema": "t", "score": 0.5, "text": "Text eins."}]
alt_g = rpl.SCAFFOLDING_VERSION
try:
    rpl.SCAFFOLDING_VERSION = "G-v5"
    p5 = rpl.baue_scaffolding_prompt("Frage?", chunks)
    check("V13 G-v5: L6 und L7 im Prompt", "L6 Gib Ergebnisse in der Einheit" in p5 and "L7 Nenne Zahlen" in p5 and "L1 bis L7" in p5)
    check("V13 G-v5: keine Fachwörter in L6/L7 (P1)", not __import__("re").search(r"scheinleistung|drehzahl|kva|\bhz\b", p5.lower()))
    rpl.SCAFFOLDING_VERSION = "G-v4"
    p4 = rpl.baue_scaffolding_prompt("Frage?", chunks)
    check("V13 G-v4 unverändert: kein L6", "L6" not in p4 and "L1 bis L5" in p4)
    check("V13: Stufen-Marker G-v5 vorhanden", "G-v5" in rpl.SCAFFOLDING_MARKER_VERSIONEN and rpl.ist_g_version("G-v5"))
finally:
    rpl.SCAFFOLDING_VERSION = alt_g

print(f"\n{ok} bestanden, {fail} fehlgeschlagen")
_sys.exit(1 if fail else 0)

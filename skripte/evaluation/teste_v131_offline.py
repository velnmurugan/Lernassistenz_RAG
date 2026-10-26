"""Offline-Test V13.1 (RP-v7, RB-v4). Ohne Ollama. Fälle aus N100 (V11B-Lauf 21 Okt, V12.9-Lauf 24 Okt).
Start (aus ~/RAG): python skripte/evaluation/teste_v131_offline.py"""
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

# Antworten aus dem N100-Lauf V13A/V13B (26.10.2026), unverändert übernommen
FAELLE = {
 "F7A": {
  "frage": "Ein Durchlauferhitzer erwärmt 0,2 Liter Wasser pro Sekunde von 15 °C auf 45 °C bei einem Wirkungsgrad von 80 %. Welche elektrische Leistung nimmt er auf?",
  "loesung": "Die elektrische Leistung beträgt 19,45 kW.\nBegründung: Aus dem Lernmaterial (Beispiel 1.21) wird der Rechenweg übernommen: Zuerst den Wärmestrom φ berechnen mit φ = m · C · Δθ / t, dann die benötigte elektrische Leistung P durch Division des Wärmestroms durch den Wirkungsgrad η ermitteln (P = φ / η).\nRechnung:\nm = 0,2 kg/s (da 1 Liter Wasser 1 kg entspricht)\nC = 4187 J/(°C·kg)\nΔθ = 30 °C (45°C - 15°C)\nt = 1 s\nφ = 0,2 kg/s · 4187 J/(°C·kg) · 30 °C / 1 s = 25.122 J/s = 25,122 kW\nη = 80 % = 0,8\nP = 25,122 kW / 0,8 = 31,4025 kW"
 },
 "F4B": {
  "frage": "Wie viel Energie ist in einer Knopfzelle gespeichert, die bei 1,35 V eine Ladung von 5 mAh liefert?",
  "loesung": "Die Knopfzelle liefert eine elektrische Energie von 23,5 mWh. Dies ergibt sich aus der Formel W = U · Q, indem man die Spannung U = 1,35 V mit der Ladung Q = 5 mAh multipliziert (W = 1,35 V · 5 mAh = 6,75 mWh? Nein, Rechnung prüfen: 1,35 * 5 = 6,75. Warte, ich muss die Rechnung im Lernmaterial genau prüfen. Im Text steht: \"Die Ladung dieser Ausführung beträgt etwa Q = 5 mAh bei U = 1,35 V.\" Die Energie ist das Produkt aus Spannung und Ladung. 1,35 * 5 = 6,75 mWh. Warum habe ich oben 23,5 geschrieben? Ah, vielleicht habe ich eine andere Zahl im Kopf. Ich muss die Rechnung neu machen: W = U * Q. U = 1,35 V. Q = 5 mAh. W = 1,35 * 5 = 6,75 mWh. Okay, das ist das korrekte Ergebnis. Meine vorherige Überlegung war falsch. Ich schreibe die Lösung mit dem korrekten Wert.)"
 },
 "F61B": {
  "frage": "Ein Motor (J0 = 0,02 kgm²) treibt über ein Getriebe eine Welle mit J1 = 1,5 kgm² an, die mit n/10 dreht. Wie groß ist das auf die Motordrehzahl umgerechnete Trägheitsmoment?",
  "loesung": "Das auf die Motordrehzahl umgerechnete Trägheitsmoment beträgt 0,015 kgm². Die Berechnung erfolgt nach Gl. 5.4 mit J = J0 + J1 · (n1/n)²; hier ist das Übersetzungsverhältnis n1/n gleich 1/10."
 },
 "F62B": {
  "frage": "Eine Last von 500 kg bewegt sich mit 0,5 m/s geradlinig; der Motor dreht mit 1000 1/min. Welches Ersatzträgheitsmoment hat die Last an der Motorwelle?",
  "loesung": "Das Ersatzträgheitsmoment der Last an der Motorwelle beträgt 0,0114 kg·m². Die Berechnung erfolgt mit der Formel J_e = m_g (v/ω)² aus dem Lernmaterial. Eingesetzt werden die Werte m_g = 500 kg und v = 0,5 m/s. Für ω wird die Winkelgeschwindigkeit berechnet: ω = 2 · π · n mit n = 1000 /min ≈ 16,67 /s (Umrechnung von min in s). Das Ergebnis ist J_e = 500 kg · (0,5 m/s / 16,67 /s)² = 0,0114 kg·m²."
 },
 "F4A": {
  "frage": "Wie viel Energie ist in einer Knopfzelle gespeichert, die bei 1,35 V eine Ladung von 5 mAh liefert?",
  "loesung": "Die Knopfzelle liefert eine elektrische Energie von 23,5 mWh.\nBegründung: Im Lernmaterial steht für diese Ausführung eine Ladung Q = 5 mAh bei einer Spannung U = 1,35 V. Die gespeicherte Energie berechnet sich aus dem Produkt von Spannung und Ladung (W = U · Q).\nRechenweg: W = 1,35 V · 5 mAh = 6,75 mWh? Nein, hier muss man aufpassen. Das Lernmaterial gibt die Werte an, aber keine explizite Formel für Energie aus Spannung und Kapazität in diesem Abschnitt (nur im Induktivitäts-Teil)."
 },
 "F61A": {
  "frage": "Ein Motor (J0 = 0,02 kgm²) treibt über ein Getriebe eine Welle mit J1 = 1,5 kgm² an, die mit n/10 dreht. Wie groß ist das auf die Motordrehzahl umgerechnete Trägheitsmoment?",
  "loesung": "Das auf die Motordrehzahl umgerechnete Trägheitsmoment beträgt 0,015 kgm².\nBegründung: Nach Gl. 5.4 wird das Trägheitsmoment einer Schwungmasse mit dem Quadrat der Übersetzung auf die Motorwelle umgerechnet. Die Übersetzung ist hier n₁/n = 1/10. Es gilt also J = J₀ + J₁ · (n₁/n)² = 0,02 kgm² + 1,5 kgm² · (1/10)² = 0,02 kgm² + 0,015 kgm² = 0,035 kgm²."
 }
}

# --- 1. Tokenizer RP-v7 (F7, F61, F62) und RP-v6 unverändert
F = FAELLE
b6 = [x["text"] for x in rp.pruefe(F["F7A"]["loesung"], F["F7A"]["frage"], "RP-v6")]
b7 = [x["text"] for x in rp.pruefe(F["F7A"]["loesung"], F["F7A"]["frage"], "RP-v7")]
check("V13.1 F7: RP-v6 unverändert (Fehllesung 30 / 1 bleibt in v6)", any("30 / 1" in t for t in b6))
check("V13.1 F7: RP-v7 liest J/(°C·kg) als Einheit, nur Kopfsatz-Befund", b7 == ["Der erste Satz nennt 19,45, die Rechnung ergibt aber 31,4025"])
b7 = [x["text"] for x in rp.pruefe(F["F61A"]["loesung"], F["F61A"]["frage"], "RP-v7")]
check("V13.1 F61: kgm² als Einheit, Rechnung ergibt 0,035", b7 == ["Der erste Satz nennt 0,015, die Rechnung ergibt aber 0,035"])
b7 = [x["text"] for x in rp.pruefe(F["F62B"]["loesung"], F["F62B"]["frage"], "RP-v7")]
check("V13.1 F62: n statt ω im Rechenweg erkannt (/s nach Zahl)", any("0,4498" in t for t in b7))
check("V13.1: '1500 1/min' bleibt Einheit", not rp.pruefe("Die Drehzahl beträgt n = 1500 1/min · 2 = 3000 1/min.", "Drehzahl?", "RP-v7"))
check("V13.1: Division durch Zahl bleibt Rechnung", bool(rp.pruefe("Es gilt v = 100 m / 20 s = 4 m/s.", "v?", "RP-v7")))
check("V13.1: 25 kV/m = 25.000 V/m ok", not rp.pruefe("E = 500 V / 0,02 m = 25.000 V/m = 25 kV/m.", "E?", "RP-v7"))

# --- 2. Bereinigung mitten im Satz (F4)
t, weg = rp.bereinige_ueberlegung_v7(F["F4B"]["loesung"])
check("V13.1 F4: Denktext ab '? Nein' entfernt, Klammer geschlossen", weg.startswith("? Nein") and "Warte" not in t and t.count("(") == t.count(")"))
check("V13.1: normale Lösung bleibt", rp.bereinige_ueberlegung_v7("Die Stromstärke beträgt 2,5 A. Begründung: I = Q / t = 50 C / 20 s = 2,5 A.")[1] == "")
check("V13.1: 'Nein' als Antwortwort bleibt", rp.bereinige_ueberlegung_v7("Nein, ein Federring reicht nicht unbedingt aus, weil nur die Mutter gesichert ist.")[1] == "")

# --- 3. Kopfsatz angleichen
kons = [x for x in rp.pruefe(t, F["F4B"]["frage"], "RP-v7") if x.get("art") == "konsistenz"]
neu = rp.korrigiere_kopf(t, kons[0]) if kons else None
check("V13.1 F4: Kopfsatz 23,5 -> 6,75 mWh", bool(neu) and neu.startswith("Die Knopfzelle liefert eine elektrische Energie von 6,75 mWh"))
check("V13.1: andere Einheit -> keine Angleichung", rp.korrigiere_kopf("Die Leistung beträgt 19 kW. Rechnung: P = 2 · 15700 W = 31400 W.",
      {"art": "konsistenz", "text": "Der erste Satz nennt 19, die Rechnung ergibt aber 31400"}) is None)

# --- 4. Ablauf mit simuliertem Modell (RP-v7)
CH = {"id": "c1", "thema": "t", "score": 0.8, "text": "Gl. 5.4: J = J0 + J1 (n1/n)²; φ = m · C · Δθ / t; P = φ / η; W = U · Q"}
def lauf(fall, antworten, version="RP-v7"):
    q = F[fall]["frage"]; aufrufe = []
    folge = iter(antworten)
    def llm(p, **k):
        aufrufe.append(p); return next(folge)
    rpl.frage_llm = llm
    rpl.RECHEN_PRUEFUNG_VERSION = version
    st = rpl.rechnung_pruefen("…\n### Frage\n" + q + "\n\nAntworte genau …", {"status": "BEANTWORTET", "loesung": F[fall]["loesung"], "hinweis": "h"}, q, [CH])
    return st, aufrufe
UNBRAUCHBAR = "FORMEL: x\nWERTE:\nRECHNUNG:\nunendlich mal\nERGEBNIS: x"
def wieder(loesung): return "STATUS: BEANTWORTET\nLÖSUNG: " + loesung + "\nÜBERLEGUNG: x\nHINWEIS: h"
alt = rpl.frage_llm, rpl.SCAFFOLDING_VERSION, rpl.RECHEN_PRUEFUNG_VERSION
try:
    rpl.SCAFFOLDING_VERSION = "G-v5"
    # F7: RB unbrauchbar (2x), Neuschreiben wiederholt den Fehler -> Kopfsatz angleichen
    st, auf = lauf("F7A", [UNBRAUCHBAR, UNBRAUCHBAR, wieder(F["F7A"]["loesung"])])
    check("V13.1 F7 Ablauf: kopf_korrigiert 31,4025 kW", st["rechen_pruefung"] == "kopf_korrigiert" and st["loesung"].startswith("Die elektrische Leistung beträgt 31,4025 kW"))
    check("V13.1 F7 Ablauf: kein Warnvermerk, Original im Log", "⚠" not in st["loesung"] and "19,45" in st["loesung_original"])
    check("V13.1 RB-v4: erster Aufruf RB-v2-Prompt, Retry RB-v3-Prompt", "Schreibweise (wichtig" not in auf[0] and "Schreibweise (wichtig" in auf[1])
    check("V13.1 RB-v4 im Log", "RB-v4 nicht verwertbar" in st["rechen_befund"] and "Retry (RB-v3)" in st["rechen_befund"])
    # F4: Denktext + falscher Kopfsatz; RB-v2 rechnet mit Faktor 3600 aus GRUNDWISSEN (Formel nicht belegt)
    RB4 = "FORMEL: W = U*Q\nWERTE:\nU = 1.35 V\nQ = 5 mAh\nRECHNUNG:\nW = U*Q/3600\nERGEBNIS: W\nEINHEIT: J\nQUELLE: GRUNDWISSEN"
    st, auf = lauf("F4B", [RB4, wieder(F["F4B"]["loesung"])])
    check("V13.1 F4 Ablauf: kopf_korrigiert 6,75 mWh, Denktext weg", st["rechen_pruefung"] == "kopf_korrigiert" and "6,75 mWh" in st["loesung"].split(".")[0] and "Warte" not in st["loesung"])
    check("V13.1 F4 Ablauf: Nachrechnungswert nicht im Text", "0,001875" not in st["loesung"])
    # F61 (V13B): Kopfsatz 0,015 ohne Rechnung; RB-v2 rechnet richtig mit belegter Formel; Neuschreiben bleibt falsch -> ersetzt
    RB61 = "FORMEL: J = J0 + J1*(n1/n)**2\nWERTE:\nJ0 = 0.02 kgm2\nJ1 = 1.5 kgm2\nv = 1/10\nRECHNUNG:\nJ = J0 + J1*v**2\nERGEBNIS: J\nEINHEIT: kgm²\nQUELLE: Gl. 5.4: J = J0 + J1 (n1/n)²"
    st, auf = lauf("F61B", [RB61, wieder(F["F61B"]["loesung"])])
    check("V13.1 F61 Ablauf: ersetzt durch 0,035", st["rechen_pruefung"] == "ersetzt" and "0,035" in st["loesung"])
    # F62 (V13B): n statt ω erkannt, Neuschreiben richtig -> nachgebessert
    gut62 = ("Das Ersatzträgheitsmoment beträgt 0,0114 kg·m². Begründung: J_e = m (v/ω)² mit ω = 2 · π · 1000/60 s⁻¹ = 104,7 s⁻¹; "
             "J_e = 500 kg · (0,5 / 104,7)² = 0,0114 kg·m².")
    st, auf = lauf("F62B", [UNBRAUCHBAR, UNBRAUCHBAR, wieder(gut62)])
    check("V13.1 F62 Ablauf: nachgebessert mit ω", st["rechen_pruefung"] == "nachgebessert" and "104,7" in st["loesung"])
    # Warnvermerk ohne ungestützte Nachrechnung: Rechenfehler + RB ohne Quelle widerspricht, Neuschreiben scheitert
    Q = "Ein Widerstand von 46 Ω liegt an 230 V. Wie groß ist der Strom?"
    F["X"] = {"frage": Q, "loesung": "Der Strom beträgt 6 A. Begründung: I = U / R = 230 V / 46 Ω = 6 A."}
    RBX = "FORMEL: I = U/R*2\nWERTE:\nU = 230 V\nR = 46 Ohm\nRECHNUNG:\nI = U/R*2\nERGEBNIS: I\nEINHEIT: A\nQUELLE: GRUNDWISSEN"
    st, auf = lauf("X", [RBX, wieder(F["X"]["loesung"])])
    check("V13.1: markiert, Vermerk ohne Nachrechnung ohne Quelle", st["rechen_pruefung"] == "markiert" and "ergibt 5" in st["loesung"] and "Nachrechnung" not in st["loesung"])
    # RP-v6 unverändert: F7 bleibt markiert (Referenzverhalten V13A)
    st, auf = lauf("F7A", [UNBRAUCHBAR, UNBRAUCHBAR, wieder(F["F7A"]["loesung"])], "RP-v6")
    check("V13.1: RP-v6 reproduziert V13A (F7 markiert)", st["rechen_pruefung"] == "markiert")
finally:
    rpl.frage_llm, rpl.SCAFFOLDING_VERSION, rpl.RECHEN_PRUEFUNG_VERSION = alt

print(f"\n{ok} bestanden, {fail} fehlgeschlagen")
_sys.exit(1 if fail else 0)

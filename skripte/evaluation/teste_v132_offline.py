"""Offline-Test V13.2 (RP-v8). Ohne Ollama. Fälle aus N100 (V11B-Lauf 21 Okt, V12.9-Lauf 24 Okt).
Start (aus ~/RAG): python skripte/evaluation/teste_v132_offline.py"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import rag_pipeline as rpl
import rechenpruefung as rp

ok = fail = 0
def check(name, cond):
    global ok, fail
    ok += bool(cond); fail += (not cond)
    print(("PASS " if cond else "FAIL ") + name)

# Entwicklungsfall Käfigläufer (App-Test 26.10.2026, interaktionen.csv 17:33:49), Antwort gekürzt, Denktext entfernt
FRAGE = ("Ein Käfigläufermotor (50 Hz, synchrone Drehzahl 1500 min⁻¹) hat bei 20 °C den Kippschlupf sK = 0,25 und bei "
         "Bemessungsmoment MN die Drehzahl nN = 1455 min⁻¹. Der Läuferkäfig aus Aluminium erwärmt sich im Betrieb auf 150 °C. "
         "Welche Drehzahl hat der Motor im betriebswarmen Zustand bei MN?")
ANTWORT = ("Die Drehzahl im betriebswarmen Zustand beträgt 1401 min⁻¹.\nBegründung: Im Lernmaterial wird in Beispiel 4.12 gezeigt, "
           "wie sich der Kippschlupf durch Erwärmung ändert. In Aufgabe 4.9 wird nachgewiesen, dass ein erhöhter Kippschlupf zu einer "
           "niedrigeren Drehzahl führt: Bei einem Ausgangswert von n_N = 1440 min⁻¹ ergibt sich ein neuer Wert von n_Nw = 1401 min⁻¹.")
MATERIAL = ("Mit Gl. 1.12b und ϑ0 = 225 °C für Aluminium erhält man die Beziehung Rrw/Rr = (225 + ϑw)/(225 + ϑu) = 1,65. "
            "Damit ergibt sich der betriebswarme Kippschlupf sKw = 1,65 · sK = 0,33. Aufgabe 4.9: Wie wirkt sich der erhöhte "
            "Kippschlupf auf die Drehzahl bei MN aus, wenn bei 20 °C der Wert nN = 1440 min⁻¹ gilt? Ergebnis: nNw = 1401 min⁻¹")
CHUNK = {"id": "fischer_pdf_0913", "thema": "4.3 Drehstrom-Asynchronmaschinen", "score": 0.7, "text": MATERIAL}

# --- 1. Befund "aus Buchbeispiel übernommen"
b = rp.pruefe_uebernahme(ANTWORT, FRAGE, MATERIAL)
check("V13.2 Übernahme erkannt (1401 aus dem Buch, keine Rechnung)", len(b) == 1 and "1401" in b[0]["text"] and b[0]["art"] == "uebernahme")
mit_rechnung = "Die Drehzahl beträgt 1431 min⁻¹. Begründung: s = 0,03 · 1,53 = 0,0459; n = 1500 · (1 - 0,0459) = 1431 min⁻¹."
check("V13.2 mit eigener Rechnung kein Befund", not rp.pruefe_uebernahme(mit_rechnung, FRAGE, MATERIAL + " 1431"))
check("V13.2 Wert nicht im Material: kein Befund", not rp.pruefe_uebernahme(ANTWORT.replace("1401", "1431"), FRAGE, MATERIAL))
check("V13.2 Frage mit weniger als zwei Zahlen: kein Befund", not rp.pruefe_uebernahme("Die Spannung beträgt 3,6 V.", "Welche Spannung liefert eine Li-Ionen-Zelle?", "Die Zelle liefert 3,6 V."))
check("V13.2 Zahl aus der Frage im ersten Satz: kein Befund", not rp.pruefe_uebernahme("Bei 1455 min⁻¹ und 150 °C sinkt die Drehzahl.", FRAGE, MATERIAL + " 1455"))
check("V13.2 pruefe() unverändert (Übernahme nicht in pruefe)", not any(x.get("art") == "uebernahme" for x in rp.pruefe(ANTWORT, FRAGE, "RP-v8")))

# --- 2. Ablauf mit simuliertem Modell
RB_FALSCH = ("FORMEL: f = (t0 + t_w)/(t0 + t_u); s_Nw = ((n_s - n_N)/n_s)/f; n_Nw = n_s*(1 - s_Nw)\nWERTE:\nt0 = 225 °C\nt_w = 150 °C\n"
             "t_u = 20 °C\nn_s = 1500 1/min\nn_N = 1455 1/min\nRECHNUNG:\nf = (t0 + t_w)/(t0 + t_u)\ns_Nw = ((n_s - n_N)/n_s)/f\n"
             "n_Nw = n_s*(1 - s_Nw)\nERGEBNIS: n_Nw\nEINHEIT: 1/min\nQUELLE: Rrw/Rr = (225 + ϑw)/(225 + ϑu)")
RB_RICHTIG = RB_FALSCH.replace("s_Nw = ((n_s - n_N)/n_s)/f", "s_Nw = ((n_s - n_N)/n_s)*f")
WIEDER = "STATUS: BEANTWORTET\nLÖSUNG: " + ANTWORT + "\nÜBERLEGUNG: x\nHINWEIS: h"
PROMPT = "…\n### Frage\n" + FRAGE + "\n\nAntworte genau …"

def lauf(version, rb1, rb_bestaetigung):
    aufrufe = []
    def llm(p, **k):
        aufrufe.append(p)
        if "Du rechnest eine Aufgabe aus der Technik nach" in p:
            return rb_bestaetigung if "Schreibweise (wichtig" in p else rb1
        return WIEDER
    rpl.frage_llm = llm
    rpl.RECHEN_PRUEFUNG_VERSION = version
    st = rpl.rechnung_pruefen(PROMPT, {"status": "BEANTWORTET", "loesung": ANTWORT, "hinweis": "h"}, FRAGE, [CHUNK])
    return st, aufrufe

alt = rpl.frage_llm, rpl.SCAFFOLDING_VERSION, rpl.RECHEN_PRUEFUNG_VERSION
try:
    rpl.SCAFFOLDING_VERSION = "G-v5"
    st, auf = lauf("RP-v7", RB_FALSCH, RB_RICHTIG)
    check("V13.2 RP-v7 reproduziert den Fehler (ersetzt durch 1471)", st["rechen_pruefung"] == "ersetzt" and "1471" in st["loesung"])
    st, auf = lauf("RP-v8", RB_FALSCH, RB_RICHTIG)
    check("V13.2 RP-v8: falsche Nachrechnung nicht bestätigt -> markiert", st["rechen_pruefung"] == "markiert")
    check("V13.2 RP-v8: kein 1471 im sichtbaren Text, Vermerk vorhanden", "1471" not in st["loesung"] and "⚠" in st["loesung"])
    check("V13.2 RP-v8: Übernahme-Vermerk sichtbar", "steht so im Lernmaterial" in st["loesung"])
    check("V13.2 RP-v8: Bestätigung im Log", "Bestätigung: nicht bestätigt" in st["rechen_befund"] and "1431" in st["rechen_befund"])
    check("V13.2 RP-v8: Bestätigungsaufruf mit RB-v3-Prompt", sum("Schreibweise (wichtig" in p for p in auf) == 1)
    st, auf = lauf("RP-v8", RB_RICHTIG, RB_RICHTIG)
    check("V13.2 RP-v8: bestätigte Nachrechnung ersetzt (1431)", st["rechen_pruefung"] == "ersetzt" and "1431" in st["loesung"] and "Bestätigung: ja" in st["rechen_befund"])
    st, auf = lauf("RP-v8", RB_FALSCH, "kaputt")
    check("V13.2 RP-v8: zweite Nachrechnung unbrauchbar -> nicht ersetzt", st["rechen_pruefung"] == "markiert" and "1471" not in st["loesung"])
    # Antwort mit richtiger eigener Rechnung und passender Nachrechnung: kein Befund, keine Bestätigungs-Kosten
    ANTWORT_GUT = mit_rechnung
    aufrufe = []
    def llm2(p, **k):
        aufrufe.append(p); return RB_RICHTIG
    rpl.frage_llm = llm2; rpl.RECHEN_PRUEFUNG_VERSION = "RP-v8"
    st = rpl.rechnung_pruefen(PROMPT, {"status": "BEANTWORTET", "loesung": ANTWORT_GUT, "hinweis": "h"}, FRAGE, [CHUNK])
    check("V13.2 richtige Antwort: ok, ein einziger RB-Aufruf", st["rechen_pruefung"] == "ok" and len(aufrufe) == 1)
finally:
    rpl.frage_llm, rpl.SCAFFOLDING_VERSION, rpl.RECHEN_PRUEFUNG_VERSION = alt

# --- 3. App: Kopfzeile ohne grünes Häkchen bei ersetzt
app = open(next(p for p in (_pl.Path("app.py"), _pl.Path("lernassistent/app.py")) if p.exists()), encoding="utf-8").read()
check("V13.2 App: eigener Kopf für ersetzt", "Lösung aus der Python-Nachrechnung" in app and '"ersetzt": "ersetzt"' in app)
check("V13.2 App: Standard-KB v7r", "knowledge_base_fischer_boege_v7r.json" in app)

print(f"\n{ok} bestanden, {fail} fehlgeschlagen")
_sys.exit(1 if fail else 0)

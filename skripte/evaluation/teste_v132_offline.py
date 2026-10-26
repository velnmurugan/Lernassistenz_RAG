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

# --- 2b. Meta-Bemerkungen (App-Test 26.10.2026, zweiter Lauf)
LECK = ANTWORT + " Da deine Fragestellung eine ähnliche Situation beschreibt, gilt der Effekt.\n*(Hinweis zur Logik für dich: Das Lernmaterial liefert in Aufgabe 4.9 direkt das Ergebnis. Die Regel L5 sagt: übernimm nur den Rechenweg. Aber streng genommen: Die Werte passen nicht genau (1455 vs 1440).)."
t, weg = rp.bereinige_ueberlegung_v8(LECK)
check("V13.2 Meta-Bemerkung ab '*(Hinweis zur Logik' entfernt", weg.startswith("*(Hinweis zur Logik") and "Regel L5" not in t and t.endswith("gilt der Effekt."))
check("V13.2 normale Lösung bleibt", rp.bereinige_ueberlegung_v8("Der Strom beträgt 5 A. Begründung: Nach der Regel des Ohmschen Gesetzes gilt I = U/R = 230 V / 46 Ω = 5 A.")[1] == "")
check("V13.2 v7-Muster weiter erkannt", rp.bereinige_ueberlegung_v8(ANTWORT + "\n*Warte, ich muss das prüfen.*")[1].startswith("*Warte"))

# --- 2c. FS-v3: Übernahme löst die Formelsuche aus, die neue Antwort mit eigener Rechnung wird angenommen
import formelsuche as fs
LOESUNG_49 = ("4.9 Aus Gl. 4.34 Schlupf bei 20 °C s = 1 - 1440 min⁻¹ / 1500 min⁻¹ = 0,04. Bei jeweils gleichem Drehmoment MN müssen in "
              "Gl. 4.41 die Nenner gleich sein, was die Beziehung sK/s + s/sK = sKw/sw + sw/sKw ergibt. Mit s = 0,04; sK = 0,2; "
              "sKw = 0,33 entsteht die quadratische Gleichung sw² - 1,716 sw + 0,109 = 0 mit der Lösung sw = 0,066")
CH_LOES = {"id": "fischer_pdf_1259", "thema": "Berechnung der Aufgaben", "score": 0.5, "text": LOESUNG_49}
NEU = ("Die Drehzahl im betriebswarmen Zustand beträgt 1431 min⁻¹.\nBegründung: Der Läuferwiderstand steigt um den Faktor "
       "(225 + 150)/(225 + 20) = 1,531, also sKw = 1,531 · 0,25 = 0,383. Mit s = 1 - 1455/1500 = 0,03 gilt sK/s + s/sK = 8,453; "
       "aus sKw/sw + sw/sKw = 8,453 folgt sw = 0,0459 und n = 1500 · (1 - 0,0459) = 1431 min⁻¹.")
RB_NEU = ("FORMEL: sK/s + s/sK = sKw/sw + sw/sKw\nWERTE:\nsK = 0.25\ns = 0.03\nf = (225 + 150)/(225 + 20)\nRECHNUNG:\nsKw = f*sK\n"
          "c = sK/s + s/sK\nsw = (c*sKw - sqrt((c*sKw)**2 - 4*sKw**2))/2\nn = 1500*(1 - sw)\nERGEBNIS: n\nEINHEIT: 1/min\n"
          "QUELLE: sK/s + s/sK = sKw/sw + sw/sKw")
def lauf_fs(version, neu_antwort):
    alt_v = fs.FORMELSUCHE_VERSION
    fs.FORMELSUCHE_VERSION = version
    aufrufe = []
    def llm(p, **k):
        aufrufe.append(p)
        if p.startswith("Eine Rechenaufgabe aus der Technik soll gelöst werden"):
            return "Kippschlupf bei Erwärmung\nKlosssche Gleichung"
        if "Du rechnest eine Aufgabe aus der Technik nach" in p:
            return RB_NEU
        return "STATUS: BEANTWORTET\nLÖSUNG: " + neu_antwort + "\nÜBERLEGUNG: x\nHINWEIS: h"
    alt_r = rpl.retrieval
    rpl.frage_llm = llm
    rpl.retrieval = lambda q, chunks, top_k=4, methode=None: ([CH_LOES, CHUNK], [CH_LOES, CHUNK])
    try:
        ergebnis = {"zeiten": {}}
        st0 = {"status": "BEANTWORTET", "loesung": ANTWORT, "hinweis": "h", "format_fehler": [], "vollstaendig_geparst": True}
        top, pr, st = rpl._formelsuche_nachher(FRAGE, [CHUNK, CH_LOES], [CHUNK], PROMPT, st0, "hybrid_kg_rr", ergebnis)
    finally:
        rpl.retrieval = alt_r
        fs.FORMELSUCHE_VERSION = alt_v
    return top, st, ergebnis.get("formelsuche", {}), aufrufe
alt2 = rpl.frage_llm, rpl.SCAFFOLDING_VERSION
try:
    rpl.SCAFFOLDING_VERSION = "G-v5"
    top, st, info, auf = lauf_fs("FS-v2", NEU)
    check("V13.2 FS-v2 unverändert: Übernahme löst keine Suche aus", not info and st["loesung"] == ANTWORT)
    top, st, info, auf = lauf_fs("FS-v3", NEU)
    check("V13.2 FS-v3: Suche ausgelöst, Lösungs-Chunk ergänzt", info.get("ausgeloest") and "fischer_pdf_1259" in info.get("ids", []))
    check("V13.2 FS-v3: neue Antwort mit eigener Rechnung angenommen (1431)", info.get("angenommen") and "1431" in st["loesung"] and any(c["id"] == "fischer_pdf_1259" for c in top))
    check("V13.2 FS-v3: Protokolltext nennt FS-v3", fs.notiz(info).startswith("FS-v3 ausgelöst"))
    top, st, info, auf = lauf_fs("FS-v3", ANTWORT.replace("1401", "0,066"))
    check("V13.2 FS-v3: neue Antwort wieder übernommen -> erste Antwort bleibt", not info.get("angenommen") and st["loesung"] == ANTWORT)
    check("V13.2 FS-v3: richtige erste Antwort löst nichts aus", not fs.braucht_suche_v3(FRAGE, {"status": "BEANTWORTET", "loesung": NEU}, MATERIAL))
finally:
    rpl.frage_llm, rpl.SCAFFOLDING_VERSION = alt2

# --- 3. App: Kopfzeile ohne grünes Häkchen bei ersetzt
app = open(next(p for p in (_pl.Path("app.py"), _pl.Path("lernassistent/app.py")) if p.exists()), encoding="utf-8").read()
check("V13.2 App: eigener Kopf für ersetzt", "Lösung aus der Python-Nachrechnung" in app and '"ersetzt": "ersetzt"' in app)
check("V13.2 App: Standard-KB v7r", "knowledge_base_fischer_boege_v7r.json" in app)

print(f"\n{ok} bestanden, {fail} fehlgeschlagen")
_sys.exit(1 if fail else 0)

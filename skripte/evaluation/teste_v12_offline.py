"""Offline-Test V12 (FS-v1 Formelsuche, BE-v1 Bildeingabe, Rechenbaustein-Korrekturen). Ohne Ollama.
Start (aus ~/RAG): python skripte/evaluation/teste_v12_offline.py"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import os, tempfile, json
import rag_pipeline as rpl
import formelsuche as fs
import bildeingabe as be
import rechenbaustein as rb
import rechenpruefung as rp

ok = fail = 0
def check(name, cond):
    global ok, fail
    ok += bool(cond); fail += (not cond)
    print(("PASS " if cond else "FAIL ") + name)

F132 = ("Ein Magnetkran hebt einen Stahlträger mit 2,5 m Länge, Querschnitt 0,02 m² und Dichte 7850 kg/m³. "
        "Welche Flussdichte B muss der Elektromagnet mit A = 0,1 m² mindestens haben?")
TRAG = {"id": "boege_pdf_2620", "thema": "Tragkraft", "score": 0.7,
        "text": "Die Tragkraft eines Hubmagneten ist F = B² · A / (2 · μ0). Beispiel 5.3 ..."}
ALT = {"id": "x1", "thema": "Aufgabe", "score": 0.9, "text": "Aufgabe 1.30: Ein Kran hebt eine Last von 3 t. Wie groß ist die Kraft?"}
MASSE = {"id": "m1", "thema": "Dichte", "score": 0.5, "text": "Masse m = ρ · V, Gewichtskraft F = m · g"}

# --- ist_rechenfrage
check("rechenfrage: 1.32", fs.ist_rechenfrage(F132))
check("rechenfrage: Verweis zählt nicht als Zahl", not fs.ist_rechenfrage("Erkläre Aufgabe 1.32 aus Abb. 2.69, was ist ein Trafo?"))
check("rechenfrage: Wissensfrage", not fs.ist_rechenfrage("Was ist ein Transformator?"))
check("rechenfrage: leer", not fs.ist_rechenfrage(""))

# --- parse
roh = "1. Kraft zwischen Magnet und Träger\n- \"Masse aus Dichte und Volumen\"\nSuchbegriffe\nF = m g\n* Gewichtskraft\nKraft zwischen Magnet und Träger\n"
p = fs.parse(roh)
check("parse: 3 Phrasen, ohne Duplikat/Formel/Überschrift", p == ["Kraft zwischen Magnet und Träger", "Masse aus Dichte und Volumen", "Gewichtskraft"])
check("parse: max 4", len(fs.parse("\n".join(f"Begriff {chr(97+i)}xyz" for i in range(8)))) == 4)
check("parse: Zahlen verworfen", fs.parse("Kraft 5 N\nLeistung im Netz") == ["Leistung im Netz"])
check("parse: leer", fs.parse("") == [] and fs.parse(None) == [])

# --- hat_formel
check("formel: Tragkraft-Chunk", fs.hat_formel(TRAG["text"]))
check("formel: Masse-Chunk", fs.hat_formel(MASSE["text"]))
check("formel: Fließtext ohne Formel", not fs.hat_formel("Ein Hubmagnet trägt Lasten aus Eisen und Stahl."))
check("formel: Aufgabe ohne Gleichung", not fs.hat_formel(ALT["text"]))
check("formel: Wert-Angabe ohne Rechenzeichen", not fs.hat_formel("Der Wert ist x = 5"))

# --- suche (Mock)
def llm_ok(prompt, options=None):
    return "Kraft eines Hubmagneten\nMasse aus Dichte und Volumen\nGewichtskraft"
def retr(phrase, chunks, top_k=4, methode=None):
    tab = {"Kraft eines Hubmagneten": [ALT, TRAG], "Masse aus Dichte und Volumen": [MASSE], "Gewichtskraft": [MASSE, TRAG]}
    return tab.get(phrase, []), []
z, info = fs.suche(F132, [], [ALT], retr, llm_ok)
check("suche: Tragkraft-Chunk gefunden, ALT (ohne Formel) übersprungen", z and z[0]["id"] == "boege_pdf_2620")
check("suche: max 2 Zusatz-Chunks", len(z) == 2 and [c["id"] for c in z] == ["boege_pdf_2620", "m1"])
check("suche: fs_phrase gesetzt", z[0]["fs_phrase"] == "Kraft eines Hubmagneten")
check("suche: Dedupe gegen vorhandene Chunks", fs.suche(F132, [], [TRAG, MASSE], retr, llm_ok)[0] == [])
z1, _ = fs.suche(F132, [], [ALT], retr, llm_ok, max_zusatz=1)
check("suche: max_zusatz=1", len(z1) == 1)
def llm_boom(prompt, options=None): raise RuntimeError("ollama down")
zb, ib = fs.suche(F132, [], [ALT], retr, llm_boom)
check("suche: Fehler -> kein Zusatz, Fehlertext", zb == [] and "ollama down" in ib["fehler"])
def retr_boom(*a, **k): raise RuntimeError("index kaputt")
zr, ir = fs.suche(F132, [], [ALT], retr_boom, llm_ok)
check("suche: Retrieval-Fehler abgefangen", zr == [] and ir["fehler"])
check("suche: Kontext der Hauptsuche nicht verändert", fs.suche(F132, [], [ALT], retr, llm_ok) and True)
check("notiz: Inhalt", "boege_pdf_2620" in fs.notiz(info) and "Hubmagneten" in fs.notiz(info))
check("notiz: Fehler", fs.notiz(ib) == "FS Fehler")
check("prompt: ohne Aufgabe-Zahlen-Beispiele, enthält Frage", F132 in fs.baue_prompt(F132))

# --- Integration beantworte_frage
alt_fn = (rpl.retrieval, rpl.frage_llm, rpl.rechnung_pruefen, rpl.hinweis_pruefen, rpl.sicherheitspruefung, fs.FORMELSUCHE_VERSION)
aufr = {"prompts": []}
def retr_haupt(frage, chunks, top_k=4, methode=None):
    if frage == F132:
        return [ALT], [ALT]
    return retr(frage, chunks, top_k, methode)
def llm_all(prompt, model=None, options=None):
    aufr["prompts"].append(prompt)
    if prompt.startswith("Eine Rechenaufgabe aus der Technik"):
        return llm_ok(prompt)
    return "STATUS: BEANTWORTET\nLÖSUNG: B = 1 T.\nHINWEIS: h"
def integr(version):
    aufr["prompts"].clear()
    rpl.retrieval, rpl.frage_llm = retr_haupt, llm_all
    rpl.rechnung_pruefen = lambda *a, **k: None
    rpl.hinweis_pruefen = lambda *a, **k: None
    rpl.sicherheitspruefung = lambda t: (False, [])
    fs.FORMELSUCHE_VERSION = version
    ereignisse = []
    try:
        return rpl.beantworte_frage(F132, [], fortschritt=lambda *a: ereignisse.append(a)), ereignisse
    finally:
        rpl.retrieval, rpl.frage_llm, rpl.rechnung_pruefen, rpl.hinweis_pruefen, rpl.sicherheitspruefung, fs.FORMELSUCHE_VERSION = alt_fn
rpl.RELEVANZ_SCHWELLE = 0.0
erg, ev = integr("FS-v1")
hauptprompt = aufr["prompts"][-1]
check("pipeline: Zusatzchunk im Hauptprompt", "Hubmagneten" in hauptprompt)
check("pipeline: Reihenfolge Original vor Zusatz", hauptprompt.index("Aufgabe 1.30") < hauptprompt.index("Hubmagneten"))
check("pipeline: top_chunks erweitert (1+2)", len(erg["top_chunks"]) == 3 and "boege_pdf_2620" in [q["id"] for q in erg["quellen"]])
check("pipeline: rechen_befund mit FS-Notiz", "FS-v1 Suchbegriffe" in (erg.get("rechen_befund") or ""))
check("pipeline: Zeit 'suche' >= Hauptsuche", "suche" in erg["zeiten"])
check("pipeline: Quellen-Ereignis zweimal (Haupt + Zusatz)", sum(1 for e in ev if e[:2] == ("suche", "quellen")) == 2)
erg0, _ = integr("aus")
check("pipeline: FS aus = wie V11b", len(erg0["top_chunks"]) == 1 and "formelsuche" not in erg0 and "FS-v1" not in (erg0.get("rechen_befund") or ""))
check("pipeline: FS aus, kein FS-Prompt", not any(p.startswith("Eine Rechenaufgabe") for p in aufr["prompts"]))

# --- Rechenbaustein-Korrekturen
check("norm: Schreibweisen gleich", rb._norm_formel("F = B²·A/(2·μ0)") == rb._norm_formel("F = B^2*A/(2*mu0)") or
      rb._norm_formel("F = B²·A/(2·μ₀)") == rb._norm_formel("F=B²A/2μ0"))
check("lesbar: ** -> ²", "²" in rb.lesbar("B**2*A") or "^" not in rb.lesbar("B**2*A"))
check("zehnerpotenz: 10^18 kein Fehlalarm", not any("18" in str(b.get("text", "")) and "nicht" in str(b.get("text", ""))
      for b in rp.pruefe("Die Ladung beträgt 1,6 · 10^18 C.", "Wie viele Elektronen sind 1 C? Es gilt e = 1,6·10^-19 C", "RP-v5")))

# --- Bildeingabe
check("zerlege: Format", be.zerlege("AUFGABENTEXT: 1.32 Berechne $B$.\nABBILDUNG: Schaltplan mit R1") == ("1.32 Berechne B.", "Schaltplan mit R1"))
check("zerlege: mehrzeilige Abbildungsbeschreibung bleibt ganz", be.zerlege("AUFGABENTEXT: T\nABBILDUNG: Zeile1\nZeile2 R1 = 5 Ω")[1] == "Zeile1\nZeile2 R1 = 5 Ω")
check("kombiniere: Kennzeichnung, ohne Abbildung unverändert", be.kombiniere("Text", "Bild") == "Text\n\n" + be.ABB_KOPF + " Bild" and be.kombiniere("Text", "") == "Text")
check("Prompt verlangt genaue Abbildungsbeschreibung", "ablesbare Zahlenwerte" in be.PROMPT and be.BILD_OPTIONEN["num_predict"] >= 900)
check("zerlege: keine Abbildung", be.zerlege("AUFGABENTEXT: Text\nABBILDUNG: keine Abbildung")[1] == "")
check("zerlege: ohne Format = ganzer Text", be.zerlege("Nur Text 5 V")[0] == "Nur Text 5 V")
check("bereinige: LaTeX", be.bereinige(r"\frac{U}{R} \cdot 2^{2} \Omega **fett**") == "(U)/(R) · 2² Ω fett")
class R:
    def __init__(s, t, code=200): s.t, s.code = t, code
    def raise_for_status(s):
        if s.code >= 400: raise RuntimeError(f"HTTP {s.code}")
    def json(s): return {"response": s.t}
gesehen = {}
def post_ok(url, json=None, timeout=None):
    gesehen.update(json); return R("AUFGABENTEXT: Wie groß ist I bei U = 5 V und R = 10 Ω?\nABBILDUNG: keine Abbildung")
png = b"\x89PNG not really"
e = be.lies_aufgabe(png, url="http://x/api/generate", modell="m1", post=post_ok)
check("lies: Text erkannt", e["text"].startswith("Wie groß ist I") and not e["fehler"] and e["modell"] == "m1")
check("lies: Nutzlast mit Bild, think aus, T=0", gesehen["images"] and gesehen["think"] is False and gesehen["options"]["temperature"] == 0)
check("lies: leere Datei -> Fehler", be.lies_aufgabe(b"", post=post_ok)["fehler"])
check("lies: zu groß -> Fehler", "8 MB" in be.lies_aufgabe(b"x" * (be.MAX_BYTES + 1), post=post_ok)["fehler"])
check("lies: HTTP-Fehler abgefangen", be.lies_aufgabe(png, url="u", modell="m", post=lambda *a, **k: R("", 500))["fehler"])
check("lies: leerer Text -> Fehler", "weder Text" in be.lies_aufgabe(png, url="u", modell="m", post=lambda *a, **k: R("AUFGABENTEXT: \nABBILDUNG: keine"))["fehler"])
check("lies: nur Abbildung -> kein Fehler (V12.6)", not be.lies_aufgabe(png, url="u", modell="m", post=lambda *a, **k: R("AUFGABENTEXT: \nABBILDUNG: Vierpolige Maschine"))["fehler"])
with tempfile.TemporaryDirectory() as d:
    pf = _pl.Path(d) / "sub" / "bild.csv"
    be.protokolliere_bild("s1", e, e["text"], pf)
    be.protokolliere_bild("s1", e, e["text"] + " korrigiert", pf)
    import csv as _csv
    zeilen = list(_csv.DictReader(open(pf, encoding="utf-8", newline="")))
    check("protokoll: 2 Zeilen, geaendert-Flag (unverändert False, korrigiert True)", len(zeilen) == 2 and zeilen[0]["geaendert"] == "False" and zeilen[1]["geaendert"] == "True")
    e2 = {**e, "abbildung": "Schaltplan"}
    be.protokolliere_bild("s1", e2, be.kombiniere(e2["text"], "Schaltplan"), pf)
    zeilen = list(_csv.DictReader(open(pf, encoding="utf-8", newline="")))
    check("protokoll: Text + Abbildungsbeschreibung unverändert = geaendert False, roh_text enthält Rohausgabe", zeilen[2]["geaendert"] == "False" and zeilen[2]["abbildung_erkannt"] == "True" and "AUFGABENTEXT" in zeilen[2]["roh_text"])
    check("protokoll: kein Bild gespeichert", "images" not in "".join(zeilen[0].keys()) and "PNG" not in str(zeilen))

# --- FS-v2 (nur nach Fehlschlag)
S_GUT = {"status": "BEANTWORTET", "loesung": "Die Stromstärke beträgt 2,5 A. Begründung: I = Q/t."}
S_OHNE = {"status": "BEANTWORTET", "loesung": "Die Aufgabe ist im Lernmaterial nicht direkt gelöst, es fehlt die Formel."}
S_TEIL = {"status": "TEILWEISE", "loesung": "Das Lernmaterial enthält keine Formel zur Energie."}
check("v2 Auslöser: gelöste Frage -> nein", not fs.braucht_suche(F132, S_GUT))
check("v2 Auslöser: keine Zahl + Hinweis -> ja", fs.braucht_suche(F132, S_OHNE))
check("v2 Auslöser: TEILWEISE -> ja", fs.braucht_suche(F132, S_TEIL))
check("v2 Auslöser: Wissensfrage -> nein", not fs.braucht_suche("Was ist ein Trafo?", S_OHNE))
check("v2 annehmen: Zahl + BEANTWORTET", fs.antwort_hat_ergebnis({"status": "BEANTWORTET", "loesung": "B beträgt 0,31 T."}))
check("v2 annehmen: TEILWEISE nein", not fs.antwort_hat_ergebnis(S_TEIL))
check("v2 annehmen: ohne Zahl nein", not fs.antwort_hat_ergebnis(S_OHNE))
check("v2 Standard ist FS-v2", "FS-v2" in open(fs.__file__, encoding="utf-8").read().split("LERNASSISTENT_FS")[1][:60])

RB_BELEGT = ("FORMEL: F = B^2*A/(2*mu_0)\nWERTE:\nA = 0,1 m²\nRECHNUNG:\nm = 7850*0,02*2,5\nF = m*9,81\nB = sqrt(2*4*pi*1e-7*F/A)\n"
             "ERGEBNIS: B\nEINHEIT: T\nQUELLE: F = B² · A / (2 · μ0)")
RB_GRUND = RB_BELEGT.replace("QUELLE: F = B² · A / (2 · μ0)", "QUELLE: GRUNDWISSEN")
rb_antwort = [RB_BELEGT]


def integr2(roh_liste, haupt=None):
    """roh_liste: Antworten der Hauptgenerierung nacheinander. Rückgabe (ergebnis, prompts)."""
    antw = list(roh_liste); prompts = []
    def llm(prompt, model=None, options=None):
        prompts.append(prompt)
        if prompt.startswith("Eine Rechenaufgabe aus der Technik"):
            return llm_ok(prompt)
        if prompt.startswith("Du rechnest eine Aufgabe"):
            return rb_antwort[0]
        return antw.pop(0)
    rpl.retrieval, rpl.frage_llm = haupt or retr_haupt, llm
    rpl.rechnung_pruefen = lambda *a, **k: None
    rpl.hinweis_pruefen = lambda *a, **k: None
    rpl.sicherheitspruefung = lambda t: (False, [])
    fs.FORMELSUCHE_VERSION = "FS-v2"
    try:
        return rpl.beantworte_frage(F132, []), prompts
    finally:
        rpl.retrieval, rpl.frage_llm, rpl.rechnung_pruefen, rpl.hinweis_pruefen, rpl.sicherheitspruefung, fs.FORMELSUCHE_VERSION = alt_fn
ROH_OHNE = "STATUS: BEANTWORTET\nLÖSUNG: Dazu fehlt im Lernmaterial die Formel.\nHINWEIS: h"
ROH_GUT = "STATUS: BEANTWORTET\nLÖSUNG: B beträgt 0,31 T.\nHINWEIS: h"
e1, p1 = integr2([ROH_GUT])
check("v2: gelöste Frage -> keine Suche, 1 Generierung, nichts ergänzt", len(p1) == 1 and "formelsuche" not in e1 and len(e1["top_chunks"]) == 1)
e2, p2 = integr2([ROH_OHNE, ROH_GUT, ROH_GUT])
check("v2: Fehlschlag -> Suche + 2. Generierung angenommen (Formel belegt)", "0,31" in e2["loesung"] and len(e2["top_chunks"]) == 3 and e2["formelsuche"]["angenommen"])
check("v2: 2. Prompt enthält Tragkraft-Chunk, 1. nicht", "Hubmagneten" in p2[-1] and "Hubmagneten" not in p2[0])
check("v2: Quellen enthalten Zusatzchunk", "boege_pdf_2620" in [q["id"] for q in e2["quellen"]])
check("v2: Protokoll rechen_befund", "FS-v2 ausgelöst" in e2["rechen_befund"] and "angenommen: ja" in e2["rechen_befund"])
rb_antwort[0] = RB_GRUND
e2b, _ = integr2([ROH_OHNE, ROH_GUT, ROH_GUT])
check("V12.3: Formel nicht im Material -> neue Antwort verworfen, erste bleibt", "fehlt im Lernmaterial" in e2b["loesung"]
      and e2b["formelsuche"]["neu"] and not e2b["formelsuche"]["angenommen"] and e2b["formelsuche"]["formel_belegt"] is False)
rb_antwort[0] = RB_BELEGT
e3, p3 = integr2([ROH_OHNE, ROH_OHNE])
check("v2: 2. Antwort wieder ohne Zahl -> erste bleibt", "fehlt im Lernmaterial" in e3["loesung"] and len(e3["top_chunks"]) == 1
      and e3["formelsuche"]["neu"] and not e3["formelsuche"]["angenommen"] and "angenommen: nein" in e3["rechen_befund"])
def retr_leer(frage, chunks, top_k=4, methode=None):
    return ([ALT], [ALT]) if frage == F132 else ([], [])
e4, p4 = integr2([ROH_OHNE], haupt=retr_leer)
check("v2: nichts gefunden -> erste bleibt, keine 2. Generierung", len(p4) == 2 and e4["formelsuche"]["ausgeloest"] and not e4["formelsuche"]["neu"])

# --- V12.2: Rechenbaustein aus dem Live-Lauf (diagnose_rb2.py, 23 Oct 2026)
F1 = "Ein Körper trägt eine Ladung von +3 C. Wie viele Elektronen fehlen ihm, wenn 1 C einer Ladung von 6,25·10^18 Elementarladungen entspricht?"
RAW1 = ("FORMEL: n = Q / e\nQUELLE: [Quelle x]: Das Formelzeichen der Ladung ist Q, Einheit 1 Coulomb (1 C), das ist die Ladung von 6,25 · 10¹⁸ Protonen.\n"
        "WERTE:\nQ = 3 C\ne = 6,25·10^18\nRECHNUNG:\nn = 3 / (6,25·10^18)\nERGEBNIS: n\nEINHEIT: 1")
r1 = rb.rechne_v2(rb.parse_v2(RAW1), F1, "Ladung von 6,25 · 10¹⁸ Protonen. 1 C = 6,25·10^18 e")
check("V12.2 F1: 6,25·10^18 lesbar (kein wert_unlesbar)", r1.get("grund") == "" and r1["ergebnisse"])
check("V12.2 F1: Auszug ohne Gleichung belegt keine Formel", r1["formel_im_material"] is False)
F29 = "Eine B2-Brückenschaltung soll 12 V Gleichspannung liefern. Welche Wechselspannung muss sekundärseitig anliegen?"
RAW29 = ("FORMEL: U = sqrt(2) * U_d / pi\nQUELLE: Gl. 2.14\nWERTE:\nU_d = 12 V\nf_N = 50 Hz\nR_L = unendlich Ohm\n"
         "RECHNUNG:\nU = sqrt(2) * 12 / pi\nERGEBNIS: U\nEINHEIT: V")
r29 = rb.rechne_v2(rb.parse_v2(RAW29), F29, "Gl. 2.14 ...")
check("V12.2 F29: unbenutzter unlesbarer Wert (R_L = unendlich) bricht nicht ab", r29.get("grund") == "" and abs(r29["ergebnis"] - 5.4019) < 1e-3)
RAW29B = RAW29.replace("U = sqrt(2) * 12 / pi", "U = sqrt(2) * 12 / pi + R_L")
check("V12.2: benutzter unlesbarer Wert -> wert_unlesbar", rb.rechne_v2(rb.parse_v2(RAW29B), F29, "")["grund"] == "wert_unlesbar")
F62 = "Eine Last von 500 kg bewegt sich mit 0,5 m/s geradlinig; der Motor dreht mit 1000 1/min. Welches Ersatzträgheitsmoment hat die Last an der Motorwelle?"
RAW62 = ("FORMEL: J_e = m_g * (v / ω)²\nWERTE:\nm_g = 500 kg\nv = 0,5 m/s\nn = 1000/60 Hz\nω = 2 * pi * n rad/s\nRECHNUNG:\n"
         "J_e = 500 * (0,5 / (2 * pi * 1000/60))**2 kg*m**2\nERGEBNIS: J_e\nEINHEIT: kg*m**2\nQUELLE: J_e = m_g (v/ω)² (5.5)")
r62 = rb.rechne_v2(rb.parse_v2(RAW62), F62, "J_e = m_g (v/ω)² (5.5)")
check("V12.2 F62: Werte mit Namen (ω = 2·pi·n) und Einheit am Ausdruck -> 0,0114", r62.get("grund") == "" and abs(r62["ergebnis"] - 0.011399) < 1e-5)
check("V12.2: Einheit am Ausdruck wird nicht mit Namen verwechselt", rb._ohne_einheit("2 * x", {"x": 3.0}) == ("2 * x", 6.0))
check("V12.2: 'a b' mit Name b wird nicht gekürzt", rb._ohne_einheit("2 x", {"x": 3.0})[1] is None)
F55 = "Ein Asynchronmotor am 50-Hz-Netz (ns = 1500 1/min) wird mit 750 1/min entgegen der Drehfeldrichtung angetrieben. Wie groß sind Schlupf und Läuferfrequenz?"
res55 = {"ergebnis": 1.5, "ergebnisse": [("s", 1.5), ("f_2", 75.0)], "einheit": "-, Hz", "rechnung": "x", "formel": ""}
check("V12.2 F55: '100 Hz' gegen 75 Hz wird gemeldet (Toleranz ±50 war zu weit)", bool(rb.vergleiche_v2("Der Schlupf beträgt s = 2 und die Läuferfrequenz f_r = 100 Hz.", F55, res55)))
check("V12.2: gerundete ganze Zahlen bleiben erlaubt (400 ~ 380 / 415)", rp._passt(415, 400.0, 0) and rp._passt(380, 400.0, 0))
check("V12.2: Prompt hat QUELLE am Ende (nach EINHEIT)", rb.baue_prompt_v2("f", "k").index("EINHEIT:") < rb.baue_prompt_v2("f", "k").index("QUELLE:"))
SCHLEIFE = ("FORMEL: F = B^2*A/(2*mu_0)\nWERTE:\nB = 1 T\nA = 0,1 m²\nRECHNUNG:\nF = B**2*A/(2*4*pi*1e-7)\nERGEBNIS: F\nEINHEIT: N\n"
            "QUELLE: " + "Die Einheit der Flussdichte ist 1 Tesla; " * 60)
rs = rb.parse_v2(SCHLEIFE)
check("V12.2: Schleife im Zitat zerstört Rechnung nicht, Quelle gekürzt", rs and rs["schritte"] and len(rs["quelle"]) <= 400)

# --- V12.3: Rechenbaustein überschreibt Ergebnis nicht mit hingeschriebener Zahl (A/B F15, F7)
F15 = "Bei welcher Drehzahl entstehen 400 V? (50 Windungen, B = 0,8 T, d = 0,3 m, l = 0,4 m)"
RAW15 = ("FORMEL: n = U/(0,7*2*N*B*l*d*pi)\nWERTE:\nU = 400 V\nN = 50\nB = 0,8 T\nl = 0,4 m\nd = 0,3 m\nRECHNUNG:\n"
         "n = U/(0,7*2*N*B*l*d*pi)\nn = 19,298\nERGEBNIS: n\nEINHEIT: 1/s\nQUELLE: n = U/(0,7*2*N*B*l*d*pi)")
r15 = rb.rechne_v2(rb.parse_v2(RAW15), F15, "n = U/(0,7*2*N*B*l*d*pi) 0,7 2")
check("V12.3: hingeschriebene Zahl überschreibt die Rechnung nicht (18,95 statt 19,298)", r15.get("grund") == "" and abs(r15["ergebnis"] - 18.95) < 0.01)
RAW_LIT = RAW15.replace("n = U/(0,7*2*N*B*l*d*pi)\nn = 19,298", "n = 19,298")
check("V12.3: Ergebnis nur als Zahl hingeschrieben -> nicht verwertbar (literal)", rb.rechne_v2(rb.parse_v2(RAW_LIT), F15, "")["grund"] == "literal")

# --- V12.4: Bild im Eingabefeld (Streamlit AppTest, nur wenn verfügbar)
try:
    from streamlit.testing.v1 import AppTest
    import inspect, streamlit as _st
    if "accept_file" not in inspect.signature(_st.chat_input).parameters:
        print("SKIP Chat-Eingabe mit Datei: Streamlit zu alt (< 1.43), Rückfall auf Expander")
    else:
        _SRC = """
import sys; sys.path.insert(0, %r)
import streamlit as st
import bildeingabe as be
class F:
    def getvalue(self): return b"x"
class V:
    def __init__(s, text, files): s.text = text; s.files = files
    def __bool__(s): return True
be.lies_aufgabe = lambda d, **k: {"text": "Wie groß ist I bei U = 5 V und R = 10 Ω?", "abbildung": "Schaltplan", "roh": "", "sekunden": 1.0, "fehler": FEHLER, "modell": "m", "bild_hash": "abc"}
be.protokolliere_bild = lambda *a, **k: None
def fake(placeholder="", *, accept_file=False, file_type=None, **kw):
    assert accept_file is True and "png" in file_type
    if not st.session_state.get("_schon"):
        st.session_state["_schon"] = True
        return V("bitte lösen", [F()])
    return None
st.chat_input = fake
be.bildeingabe_ui()
frage = be.chat_eingabe("Frage?") or st.session_state.pop("naechste_frage", None)
st.write("FRAGE:", frage)
""" % str(_pl.Path(be.__file__).resolve().parent)
        at = AppTest.from_string(_SRC.replace("FEHLER", '""')).run(timeout=60)
        check("V12.5 Chat: Bild + Text -> sofort als Frage (kein Prüfblock), mit Abbildungsbeschreibung",
              not at.exception and not at.text_area and any(
                  "FRAGE: Wie groß ist I" in m.value and "bitte lösen" in m.value and be.ABB_KOPF in m.value and "Schaltplan" in m.value
                  for m in at.markdown))
        at2 = AppTest.from_string(_SRC.replace("FEHLER", '"Kein Text erkannt."')).run(timeout=60)
        check("V12.5 Chat: Fehlerfall zeigt Meldung und 'Schließen'", [e.value for e in at2.error] == ["Kein Text erkannt."]
              and [b.label for b in at2.button] == ["Schließen"])
        os.environ["LERNASSISTENT_BILD_PRUEFEN"] = "1"
        try:
            at3 = AppTest.from_string(_SRC.replace("FEHLER", '""')).run(timeout=60)
            check("V12.5 Prüfmodus (Entwicklung): Block mit Text und Buttons", not at3.exception and at3.text_area
                  and "U = 5 V" in at3.text_area[0].value and [b.label for b in at3.button] == ["Frage stellen", "Verwerfen"])
            at3.button(key="bild_senden").click().run(timeout=60)
            check("V12.5 Prüfmodus: Senden gibt Text + Abbildung weiter", any("FRAGE: Wie groß ist I" in m.value and be.ABB_KOPF in m.value
                                                                             for m in at3.markdown) and not at3.text_area)
        finally:
            os.environ.pop("LERNASSISTENT_BILD_PRUEFEN", None)
except ImportError:
    print("SKIP Chat-Eingabe mit Datei: streamlit.testing nicht verfügbar")

# --- V12.6: Standardfrage, Bild an Hauptantwort, App-Patch
check("V12.6 Standardfrage: leer", be.braucht_standardfrage(""))
check("V12.6 Standardfrage: nur Bildunterschrift", be.braucht_standardfrage("Bild 2.15 Gleichstrommaschine"))
check("V12.6 Standardfrage: Aufgabe nicht ersetzt", not be.braucht_standardfrage("Berechne den Pegel Lp") and not be.braucht_standardfrage("Wie groß ist L?"))
import rag_pipeline as _rp6
_gesehen = {}
class _R6:
    def raise_for_status(self): pass
    def json(self): return {"response": "x"}
_orig = _rp6.requests.post
_rp6.requests.post = lambda u, json=None, timeout=0: (_gesehen.update(json=json, timeout=timeout), _R6())[1]
_rp6.frage_llm("p"); check("V12.6 frage_llm ohne Bild: keine images", "images" not in _gesehen["json"])
_rp6.frage_llm("p", bild="QUJD"); check("V12.6 frage_llm mit Bild: images im Payload", _gesehen["json"]["images"] == ["QUJD"])
_rp6.requests.post = _orig
_app = open("app.py", encoding="utf-8").read()
check("V12.6 app.py: Bild im Chat und Verlauf", _app.count("st.image(") >= 2 and "naechstes_bild" in _app and "BILD_ANHANG" in _app)
check("V12.6 pipeline: BILD_ANHANG zurückgesetzt", _rp6.BILD_ANHANG is None)

# --- V12.7: keine erfundene Aufgabe, Thema, Suchanfrage getrennt
check("V12.7 zerlege_felder: keiner/Thema/Abbildung", be.zerlege_felder("AUFGABENTEXT: keiner\nTHEMA: Gleichstrommaschine, Pole\nABBILDUNG: Schnitt mit Polen N1 S1") == ("", "Gleichstrommaschine, Pole", "Schnitt mit Polen N1 S1"))
check("V12.7 zerlege_felder: keine Abbildung", be.zerlege_felder("AUFGABENTEXT: Berechne I.\nTHEMA: Ohm\nABBILDUNG: keine Abbildung") == ("Berechne I.", "Ohm", ""))
check("V12.7 zerlege_felder: altes Format", be.zerlege_felder("AUFGABENTEXT: A\nABBILDUNG: B") == ("A", "", "B"))
check("V12.7 Prompt verbietet erfundene Aufgabe", "Erfinde niemals eine Aufgabe" in be.PROMPT and "THEMA:" in be.PROMPT)
import importlib; importlib.reload(be)
_e = be.lies_aufgabe(png, url="u", modell="m", post=lambda *a, **k: R("AUFGABENTEXT: keiner\nTHEMA: Gleichstrommaschine\nABBILDUNG: Schnitt"))
check("V12.7 lies: Thema gesetzt, Text leer, kein Fehler", _e["text"] == "" and _e["thema"] == "Gleichstrommaschine" and not _e["fehler"])
_seen = {}
_orig_ret = _rp6.retrieval
_rp6.retrieval = lambda q, *a, **k: (_seen.update(q=q), ([], []))[1]
_rp6.RETRIEVAL_FRAGE = "Gleichstrommaschine Pole"
try:
    _rp6.beantworte_frage("erkläre diese Abbildung\n\nAbbildung ...: Transformator", [])
except Exception:
    pass
_rp6.RETRIEVAL_FRAGE = None; _rp6.retrieval = _orig_ret
check("V12.7 Suche nutzt RETRIEVAL_FRAGE statt Frage", _seen.get("q") == "Gleichstrommaschine Pole")

# --- V12.8: Bildfragen kennzeichnen
import ast as _ast, re as _re
_src = open("app.py", encoding="utf-8").read()
_fn = next(n for n in _ast.parse(_src).body if isinstance(n, _ast.FunctionDef) and n.name == "vertrauens_zeile")
_ns = {"re": _re, "quellen_gruppen": lambda e: {"a": [{"text": "x"}]}, "passende_stelle": lambda a, b: True, "bereinige_auszug": lambda x: x}
exec(compile(_ast.Module([_fn], []), "app.py", "exec"), _ns)
_e = {"status": "BEANTWORTET", "loesung": "x", "hinweis": "y"}
_vz = _ns["vertrauens_zeile"]
check("V12.8 normale Frage: grüne Marken wie bisher", _vz(_e)[0].startswith("✓ im Lernmaterial") and len(_vz(_e)) == 2)
_c = _vz(_e, bildfrage=True, thema_fehlt=True)
check("V12.8 Bildfrage ohne Thema: keine grünen Marken, neutrale Marke", _c[0].startswith("◔ beruht auf automatisch") and not any(x.startswith("✓") for x in _c))
_c2 = _vz(_e, bildfrage=True, thema_fehlt=False)
check("V12.8 Bildfrage mit Thema: neutrale Marke + Marken bleiben", _c2[0].startswith("◔ beruht") and any(x.startswith("✓") for x in _c2))
check("V12.8 Themenerkennung", not be.thema_im_text("erkläre diese abbildung") and be.thema_im_text("erkläre diese Abbildung der Gleichstrommaschine") and not be.thema_im_text(""))

# --- V12.9: Bildabgleich (optional)
import bildabgleich as _ba
check("V12.9 Bildabgleich standardmäßig aus", not _ba.aktiv())
try:
    import cv2 as _cv2, numpy as _np, tempfile as _tf, json as _json, os as _os2
    def _fig(seed):
        r = _np.random.default_rng(seed); im = _np.full((400, 500), 255, _np.uint8)
        for _ in range(40):
            _cv2.line(im, (int(r.integers(0, 500)), int(r.integers(0, 400))), (int(r.integers(0, 500)), int(r.integers(0, 400))), int(r.integers(0, 120)), 2)
        for _ in range(10): _cv2.circle(im, (int(r.integers(30, 470)), int(r.integers(30, 370))), int(r.integers(10, 40)), 0, 2)
        return im
    with _tf.TemporaryDirectory() as d:
        _os2.makedirs(d + "/images")
        ch = []
        for i in range(5):
            _cv2.imwrite(f"{d}/images/f{i}.png", _fig(i))
            ch.append({"id": f"pdf_{i:04d}", "typ": "abbildung", "bild": f"images/f{i}.png", "seite": 10 + i, "thema": f"Kap > Thema{i}", "text": f"Abbildung: Bild {i}"})
        _json.dump({"chunks": ch}, open(d + "/kb.json", "w"))
        idx = _ba.baue_index(d + "/kb.json", d, d + "/cache.pkl")
        check("V12.9 Index: 5 Abbildungen", len(idx) == 5)
        seite = _np.full((900, 700), 255, _np.uint8); seite[200:600, 100:600] = _fig(3)
        seite = _cv2.resize(seite, (560, 720)); ok_, buf = _cv2.imencode(".png", seite)
        m = _ba.finde(buf.tobytes(), idx)
        check("V12.9 Abgleich: Ausschnitt im Screenshot gefunden", m and m["chunk"]["id"] == "pdf_0003" and m["inlier"] >= 15)
        rausch = _np.random.default_rng(9).integers(0, 255, (400, 500), dtype=_np.uint8); _, b2 = _cv2.imencode(".png", rausch)
        check("V12.9 Abgleich: fremdes Bild -> kein Treffer", _ba.finde(b2.tobytes(), idx) is None)
        such, satz = _ba.fundstelle(m)
        check("V12.9 Fundstelle: Thema, Seite, Unterschrift", "Thema3" in such and "Seite 13" in satz and "Bild 3" in satz)
        check("V12.9 Index-Cache geschrieben", _os2.path.exists(d + "/cache.pkl"))
except ImportError:
    print("SKIP Bildabgleich: opencv fehlt")

print(f"\n{ok} bestanden, {fail} fehlgeschlagen")
_sys.exit(1 if fail else 0)

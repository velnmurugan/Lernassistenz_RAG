#!/usr/bin/env python3
"""
optimiere_hinweise.py  –  Hinweis-Optimierung auf den N100-Dialogzuständen (unbeaufsichtigt, ein Befehl)
-------------------------------------------------------------------------------------------------------
Anlass: Im Dialogtest HD-V2 (143 Hinweise) zeigte sich eine Schwäche beim Zurückhalten (P1): Folgehinweise
verraten oft Bausteine der Lösung, die der bisherige Check (HP-v4: nur Zahlen/Material) nicht erkennt.
Der Richter mistral-nemo stuft P1 fast durchgehend als erfüllt ein; sein Urteil ist dafür nicht belastbar.

Dieses Skript prüft, ob sich das Zurückhalten durch (a) einen Leck-Wächter und/oder (b) einen neu strukturierten
Prompt verbessern lässt, ohne die anderen Kriterien zu verschlechtern. Vorgehen (Wiedergabe ("Replay") der 143
Hinweis-Situationen aus HD-V2: gleiche Fragen, gleiche Lernenden-Antworten, gleiche Rückmeldungen; es wird nur der
Hinweis neu erzeugt):

  Phase 0  Rauchtest mit 3 Situationen (alle Phasen), danach automatisch der volle Lauf.
  Phase 1  Kalibrierung des Leck-Prüfers: zwei Prompts (C1 Bausteine-Methode, C2 direkte Frage) x bis zu drei
           Modelle gegen Referenzurteile zu P1 (aus HD-V2, fest im Skript). Auswahl des besten unabhängigen
           Prüfers (nicht das Generatormodell) für die Auswertung und des besten Prüfers mit dem
           Generatormodell für den Wächter. Kennzahl: Cohen-Kappa (Leck ja/nein) und gewichtetes Kappa (3 Stufen).
  Phase 2  Erzeugung je Situation in vier Varianten:
             B   Basis: H-v3 (Versuch 1) bzw. HD-v2 (ab Versuch 2), unverändert (gespeicherte Hinweise)
             V1  Basis + Wächter (Prüfer prüft den Entwurf; bei Leck bis zu 2 Neufassungen mit Hinweis auf das Verratene;
                 sonst neutraler Ersatzhinweis)
             V2  Prompt H-v4 (Lösungsbausteine zerlegen, genau ein Ziel wählen, offene Bausteine ausschließen,
                 Regeln P1-P6 als Formregeln, Bezug auf die letzte Antwort)
             V3  H-v4 + Wächter
           Alle Varianten laufen anschließend durch die bestehende Hinweis-Prüfung HP-v4.
  Phase 3  Auswertung: (1) Leck-Prüfer (unabhängig) je Variante und Versuch; (2) objektive Kennzahlen ohne Modell
           (Zahlleck, Lösungswortanteil, Länge, Ja/Nein-Fragen, erfundener Kontext, Wiederholung, Bezug auf die
           Antwort); (3) Rubrik P1-P6 durch den Richter (nur ergänzend); gepaarte Vergleiche mit der Basis
           (Vorzeichentest).
  Phase 4  Ausgabe: Variantentabelle, Zusammenfassung mit Empfehlung, verblindeter Bewertungsbogen für zwei
           Menschen (Hinweise aller Varianten gemischt) mit Schlüssel, Doku-Eintrag, Git-Commit.

Grenzen (stehen auch in der Zusammenfassung): Entwicklungsdaten; N100 ist kein Held-out-Satz; Replay mit festen
früheren Verläufen (die Antworten der Simulation passen zum alten Hinweis); die Leck-Prüfer sind an einem
einzelnen Satz von Referenzurteilen kalibriert; ein besserer Wert hier ist kein Beleg im Beitrag. Entscheidend ist
der Bewertungsbogen (zwei Menschen) und danach ein einmaliger Lauf auf einem Held-out-Satz mit eingefrorener Variante.

Start (aus ~/RAG, Umgebung pilot_rag aktiv, Ollama läuft, Vordergrund; Laufzeit ca. 5-7 h; bricht man ab, setzt
derselbe Befehl fort; Rechner nicht in den Ruhezustand gehen lassen):
    python skripte/evaluation/optimiere_hinweise.py
Voraussetzung: evaluationsdaten/hinweis_dialog_HD-V2_zustand.json (aus dem Dialogtest) und die Modelle
qwen3.5:9b, mistral-nemo (Richter/Prüfer) und granite4.1:8b (zweiter Prüfer; fehlt er, wird er übersprungen).
Ergebnisse: evaluationsdaten/hinweis_opt_<LABEL>_*.csv / .txt / _zustand.json
"""
import sys as _sys
import pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
import teste_hinweis_dialog as hd  # noqa: E402  (friert V11B ein, importiert die Pipeline)

import argparse  # noqa: E402
import datetime  # noqa: E402
import glob  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import random  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
from collections import Counter, defaultdict  # noqa: E402
from pathlib import Path  # noqa: E402

rp = hd.rag_pipeline
VERSION = "HO-v1"
PROMPT_NEU = "H-v4"
BASIS_LABEL = "HD-V2"
VARIANTEN = ("B", "V1", "V2", "V3")
BESCHREIBUNG = {"B": "Basis (H-v3 / HD-v2)", "V1": "Basis + Wächter", "V2": "Prompt H-v4", "V3": "H-v4 + Wächter"}
ERSATZ_HINWEIS = ("Überlege zuerst, welche Größe oder welcher Begriff in der Frage gesucht ist und wovon er abhängen "
                  "könnte. Was weißt du darüber schon?")
KLEIN = {"j": 2, "t": 1, "n": 0}
LECK_STUFE = {"kein_leck": 2, "teilweise": 1, "leck": 0}

# Referenzurteile zu P1 (j = nichts verraten, t = teilweise, n = verrät Lösungsbausteine) mit Kurzprüfsumme des
# Hinweistextes in HD-V2; dienen nur der Kalibrierung der Leck-Prüfer.
REFERENZ_P1 = {
    "F1_1": ("j", "21c6e2"),
    "F2_1": ("n", "9b392e"),
    "F3_1": ("t", "644a1e"),
    "F3_2": ("n", "300ca6"),
    "F4_1": ("t", "b414dc"),
    "F4_2": ("t", "fcaee3"),
    "F5_1": ("j", "b04292"),
    "F5_2": ("t", "379d98"),
    "F6_1": ("j", "a23d82"),
    "F6_2": ("j", "fa8916"),
    "F7_1": ("t", "07838d"),
    "F7_2": ("n", "0a5bbf"),
    "F7_3": ("n", "9733ab"),
    "F8_1": ("j", "3d28e0"),
    "F8_2": ("n", "c487f4"),
    "F10_1": ("t", "eb8d1a"),
    "F10_2": ("n", "f3eb77"),
    "F10_3": ("t", "ccb62d"),
    "F11_1": ("j", "b0e76d"),
    "F12_1": ("t", "99d4a4"),
    "F13_1": ("j", "838de9"),
    "F14_1": ("t", "df041a"),
    "F14_2": ("j", "5b0f76"),
    "F15_1": ("t", "f5c9d3"),
    "F15_2": ("j", "063121"),
    "F16_1": ("j", "0b0ab7"),
    "F17_1": ("j", "590194"),
    "F19_1": ("t", "b637e7"),
    "F20_1": ("n", "a688a4"),
    "F21_1": ("t", "8cb0e6"),
    "F22_1": ("t", "121642"),
    "F23_1": ("t", "084cf6"),
    "F23_2": ("j", "38e9cb"),
    "F24_1": ("n", "973144"),
    "F25_1": ("n", "71c12c"),
    "F25_2": ("j", "db5de6"),
    "F26_1": ("t", "d50b9d"),
    "F28_1": ("j", "997015"),
    "F28_2": ("n", "6fcfae"),
    "F28_3": ("j", "e79a3e"),
    "F29_1": ("j", "0dbc48"),
    "F29_2": ("t", "fda69f"),
    "F29_3": ("j", "10f205"),
    "F30_1": ("t", "163873"),
    "F31_1": ("t", "f59206"),
    "F32_1": ("j", "0ce486"),
    "F32_2": ("n", "0aa4db"),
    "F32_3": ("n", "3b5312"),
    "F33_1": ("j", "a3c04c"),
    "F34_1": ("j", "90f98d"),
    "F35_1": ("j", "527203"),
    "F37_1": ("t", "edcba9"),
    "F38_1": ("t", "189ed3"),
    "F38_2": ("n", "c0e2bf"),
    "F39_1": ("j", "0f2472"),
    "F40_1": ("t", "49644c"),
    "F40_2": ("t", "111a67"),
    "F41_1": ("j", "e4c32b"),
    "F42_1": ("n", "325026"),
    "F42_2": ("n", "827223"),
    "F43_1": ("n", "95476b"),
    "F44_1": ("j", "7943b4"),
    "F46_1": ("j", "85d650"),
    "F47_1": ("t", "7cfa61"),
    "F47_2": ("t", "ce8658"),
    "F48_1": ("t", "a9f76d"),
    "F49_1": ("n", "b78e57"),
    "F50_1": ("n", "4980e5"),
    "F50_2": ("n", "9f446d"),
    "F50_3": ("t", "ebec14"),
    "F51_1": ("j", "d72b1f"),
    "F52_1": ("t", "5f0231"),
    "F53_1": ("t", "7e59bb"),
    "F53_2": ("j", "2c0526"),
    "F53_3": ("n", "b41601"),
    "F55_1": ("t", "0b209f"),
    "F56_1": ("t", "45e96e"),
    "F56_2": ("n", "978d09"),
    "F57_1": ("j", "262153"),
    "F58_1": ("j", "2284ec"),
    "F58_2": ("j", "04c204"),
    "F58_3": ("j", "5425fa"),
    "F59_1": ("j", "5d7f0d"),
    "F59_2": ("t", "d5fa21"),
    "F59_3": ("n", "5b9daf"),
    "F60_1": ("j", "3964cf"),
    "F60_2": ("t", "e1ed9e"),
    "F61_1": ("n", "b57a4e"),
    "F61_2": ("t", "213507"),
    "F62_1": ("n", "4bfb8b"),
    "F64_1": ("t", "746e21"),
    "F65_1": ("t", "3d3565"),
    "F65_2": ("t", "a745e4"),
    "F66_1": ("t", "3bc2f0"),
    "F66_2": ("n", "26336b"),
    "F67_1": ("j", "4ed928"),
    "F67_2": ("t", "90e3d7"),
    "F68_1": ("j", "792fa1"),
    "F69_1": ("t", "eba025"),
    "B1_1": ("t", "4d627b"),
    "B2_1": ("j", "a3abb0"),
    "B2_2": ("n", "fd9279"),
    "B3_1": ("t", "6bc9f5"),
    "B3_2": ("t", "b8884b"),
    "B4_1": ("t", "8d122d"),
    "B5_1": ("n", "f260a9"),
    "B6_1": ("j", "f2082a"),
    "B6_2": ("n", "c44dde"),
    "B6_3": ("n", "9a0153"),
    "B7_1": ("t", "b21e4f"),
    "B8_1": ("j", "4d0d9c"),
    "B9_1": ("t", "f2c038"),
    "B10_1": ("t", "2cc427"),
    "B11_1": ("t", "d45426"),
    "B12_1": ("t", "5bb0f1"),
    "B13_1": ("j", "cffb2a"),
    "B13_2": ("j", "31f3a3"),
    "B14_1": ("n", "dcf529"),
    "B15_1": ("j", "ba7514"),
    "B15_2": ("n", "fa346b"),
    "B16_1": ("t", "a15a6d"),
    "B17_1": ("t", "e31d70"),
    "B18_1": ("j", "9b8e3b"),
    "B19_1": ("n", "972d0a"),
    "B20_1": ("t", "ae9522"),
    "B21_1": ("j", "b64dcd"),
    "B22_1": ("t", "406671"),
    "B23_1": ("j", "8299a8"),
    "B24_1": ("n", "ab8fbb"),
    "B24_2": ("j", "432552"),
    "B24_3": ("j", "ad8e3d"),
    "B25_1": ("j", "4b190a"),
    "B26_1": ("t", "82be7f"),
    "B26_2": ("n", "59253f"),
    "B27_1": ("n", "0f1c9c"),
    "B27_2": ("n", "7fbc01"),
    "B28_1": ("j", "4acd55"),
    "B28_2": ("j", "174c4d"),
    "B28_3": ("j", "c836b9"),
    "B29_1": ("j", "289661"),
    "B29_2": ("j", "0986d7"),
    "B30_1": ("j", "604287"),
    "B30_2": ("j", "110db6"),
}


# ------------------------------------------------------------------------------------------- Hilfen
def md5(text):
    return hashlib.md5((text or "").strip().encode()).hexdigest()[:6]


def lade_szenarien(basis):
    pfad = Path(f"evaluationsdaten/hinweis_dialog_{basis}_zustand.json")
    if not pfad.exists():
        raise SystemExit(f"FEHLT: {pfad}\nDer Dialogtest (teste_hinweis_dialog.py, Label {basis}) muss zuerst gelaufen sein; "
                         f"aus ~/RAG starten.")
    z = json.loads(pfad.read_text(encoding="utf-8"))
    sz = []
    for s in z["q"].values():
        if not s.get("ok"):
            continue
        for t in s["turns"]:
            if "urteil" not in t:
                continue
            sz.append({"key": f"{s['id']}_{t['n']}", "s": s, "n": t["n"], "hinweis_b": t["hinweis"],
                       "urteile_b": z.get("urteile", {}).get(f"{s['id']}-H{t['n']}", {})})
    sz.sort(key=lambda x: (x["s"]["id"], x["n"]))
    return sz


def prompt_basis(sz):
    s, n = sz["s"], sz["n"]
    if n > 1:
        return hd.baue_folgehinweis_prompt(s, s["turns"][n - 2], n)
    alt = rp._kontext_text  # H-v3 mit dem gespeicherten Kontext (identischer Text wie in der App)
    rp._kontext_text = lambda _c: s["kontext"]
    try:
        return rp.baue_hinweis_prompt(s["frage"], [], s["loesung"])
    finally:
        rp._kontext_text = alt


def prompt_neu(sz):
    s, n = sz["s"], sz["n"]
    if n > 1:
        verlauf = hd.verlauf_text(s, n - 1)
        letzte = s["turns"][n - 2]["antwort"]
        regel4 = ("Beziehe dich auf eine konkrete Stelle der letzten Antwort (greife ein Wort oder eine Zahl daraus auf). "
                  "Ist die Antwort ohne fachliche Idee, gib einen kleineren Einstieg (ein Zusammenhang zwischen zwei Größen "
                  "aus der Frage), nicht mehr Inhalt. Wiederhole keinen früheren Hinweis und keine Rückmeldung; konkreter "
                  "heißt: die Frage enger stellen, nicht mehr aus der Lösung sagen.")
        ziel_zusatz = " Enthält die letzte Antwort etwas Falsches, ist das Ziel der Baustein, den sie dort falsch hat."
        kopf = f"Die Person hat die Frage schon {n - 1}-mal versucht.\nBisheriger Verlauf:\n{verlauf}\nLetzte Antwort der Person: {letzte}"
    else:
        regel4 = ("Beginne beim Vorwissen, das für Auszubildende in diesem Stoffgebiet realistisch ist; überfordere nicht.")
        ziel_zusatz = ""
        kopf = "Die Person hat noch keinen Versuch gemacht."
    return f"""Du schreibst Hinweis Nr. {n} (von höchstens {hd.MAX_VERSUCHE}) für Auszubildende in technischen Berufen.
Die Person sieht NUR die Frage und den bisherigen Verlauf, nicht die Lernmaterialien und nicht die Lösung. Ein guter
Hinweis lässt sie den nächsten Schritt selbst finden.

Gehe genau in diesen vier Schritten vor und schreibe jeden mit seiner Überschrift:
BAUSTEINE: Zerlege die Lösung in 2 bis 5 inhaltliche Bausteine (Begriff, Aussage, Bedingung, Größe, Rechenschritt,
  Ergebnis). Markiere mit (F) Bausteine, die schon in der Frage stehen, und mit (P) solche, die die Person in ihren
  Antworten schon richtig genannt hat. Alle anderen Bausteine sind „offen".
ZIEL: Wähle genau EINEN offenen Baustein, den die Person als Nächstes selbst finden soll.{ziel_zusatz}
ABSTAND: Nenne in einem Satz alle offenen Bausteine, die im Hinweis NICHT vorkommen dürfen (auch das Ziel selbst).
HINWEIS: Der Hinweis nach diesen Regeln:
  1 Zurückhalten: Er nennt keinen offenen Baustein, weder wörtlich noch umschrieben, nicht als Definition, nicht als
    eine von zwei Möglichkeiten („A oder B?"), nicht als Aussage, der man nur zustimmen muss. Keine Formel mit
    eingesetzten Werten, kein Ergebnis.
  2 Richtung: Er zeigt auf die Stelle, an der man weiterdenkt: eine Größe, ein Zusammenhang oder ein Vergleich, der
    in der Frage oder im Verlauf steht.
  3 Eigenes Denken: Er ist eine offene Frage (Wie, Wovon, Was passiert, wenn …), keine Ja/Nein-Frage und keine
    Aufforderung, etwas nachzuschlagen oder zu prüfen.
  4 Anpassung: {regel4}
  5 Fachlich stimmig: Er behauptet nichts, was nicht in Lösung oder Lernmaterial steht; keine neuen Zahlen.
  6 Zugänglich: Höchstens zwei kurze Sätze, Anrede mit „du", nie „im Text", „im Material", „in der Quelle", nie
    „du hast gesehen/gelernt/gelesen".

Beispiel nur für die Form (anderes Thema):
Frage: Warum kocht Wasser auf einem hohen Berg schon unter 100 °C?
BAUSTEINE: (1) Siedepunkt hängt vom Umgebungsdruck ab; (2) Luftdruck sinkt mit der Höhe; (3) Wasser siedet, wenn der Dampfdruck dem Umgebungsdruck entspricht.
ZIEL: Baustein (1).
ABSTAND: Nicht nennen: Abhängigkeit des Siedepunkts vom Druck, sinkender Luftdruck, Dampfdruck gleich Umgebungsdruck.
HINWEIS: Wodurch unterscheiden sich die Bedingungen für das Wasser im Topf auf dem Berg von denen im Tal, und was davon könnte das Sieden beeinflussen?
Schlecht wäre: „Auf dem Berg ist der Luftdruck geringer; wie hängt der Siedepunkt vom Druck ab?" (nennt offene Bausteine).

{kopf}

Lernmaterialien:
{s['kontext']}

Frage: {s['frage']}

Lösung (GEHEIM, nicht verraten):
{s['loesung']}

Schreibe jetzt die vier Schritte."""


def erzeuge(prompt, s):
    roh = rp.frage_llm(prompt, options=rp.GENERIERUNGS_OPTIONEN)
    h, _ = rp.parse_hinweis(roh)
    if not h:
        return "", "format_fehler"
    st = {"hinweis": h, "loesung": s["loesung"], "status": s["status"]}
    rp.hinweis_pruefen(s["frage"], st)
    return st["hinweis"], st.get("hinweis_pruefung", "")


# ---------------------------------------------------------------------------------- Leck-Prüfer
def pruefer_prompt(pid, sz, hinweis):
    s, n = sz["s"], sz["n"]
    verlauf = hd.verlauf_text(s, n - 1) if n > 1 else "(noch kein Versuch)"
    kopf = f"""### Frage
{s['frage']}

### Richtige Lösung (Referenz; die lernende Person kennt sie nicht)
{s['loesung']}

### Bisheriger Verlauf (Hinweise, Antworten der Person, Rückmeldungen)
{verlauf}

### Zu prüfender Hinweis (Hinweis Nr. {n})
{hinweis}
"""
    if pid == "C1":
        return f"""Du prüfst, ob ein Hinweis für Lernende die Lösung verrät. Ein Hinweis soll zum Nachdenken anregen und darf die
Lösung nicht vorwegnehmen.

{kopf}
Vorgehen:
1. BAUSTEINE: Zerlege die Lösung in höchstens 6 kurze inhaltliche Bausteine (Begriff, Aussage, Bedingung, Größe,
   Rechenschritt, Ergebnis).
2. Streiche Bausteine, die schon in der Frage oder in den Antworten der Person stehen.
3. GENANNT: Welche der übrigen Bausteine kommen im Hinweis vor – wörtlich, umschrieben, als Definition, als eine von zwei
   Möglichkeiten in einer Entweder-oder-Frage, als vollständige Liste oder als Aussage, der man nur zustimmen muss? Nenne sie kurz
   oder schreibe „keine".
4. URTEIL: leck = mindestens ein zentraler offener Baustein wird genannt; teilweise = nur ein Randbegriff oder ein Teil davon;
   kein_leck = keiner. Eine reine Wiederholung der Frage oder ein Verweis auf eine Größe, die in der Frage steht, ist kein Leck.

Antworte genau in diesem Format:
BAUSTEINE: <Liste>
GENANNT: <Liste oder keine>
URTEIL: <leck oder teilweise oder kein_leck>"""
    return f"""Du prüfst streng, ob ein Hinweis für Lernende die Lösung verrät.

{kopf}
Frage dich: Kann eine Person, die nur die Frage, den Verlauf und diesen Hinweis kennt, daraus schon einen zentralen Teil der
Lösung ablesen oder durch bloßes Zustimmen übernehmen (genannter Begriff, genannte Bedingung, Richtung des Ergebnisses,
richtige Option einer Entweder-oder-Frage, Formelaufbau, Name der gesuchten Sache)? Dann ist es ein Leck.
leck = ja, ein zentraler Teil ist ablesbar; teilweise = nur ein Randbegriff oder ein kleiner Teil; kein_leck = der Hinweis
lenkt nur auf eine Größe oder einen Zusammenhang, ohne etwas von der Lösung zu nennen. Wiederholungen aus der Frage zählen nicht.

Antworte genau in diesem Format:
GENANNT: <was ablesbar ist, in höchstens 15 Wörtern, oder keine>
URTEIL: <leck oder teilweise oder kein_leck>"""


def parse_pruefer(roh):
    u = re.findall(r"(?i)URTEIL\W*[:=]\W*(kein[_ ]leck|teilweise|leck)", roh or "")
    g = re.findall(r"(?im)^\W*GENANNT\W*[:=]\s*(.+)$", roh or "")
    urteil = u[-1].lower().replace(" ", "_") if u else ""
    return {"urteil": urteil, "genannt": (g[-1].strip() if g else "")[:300]}


def leck_pruefung(cfg, sz, hinweis, zustand):
    modell, pid = cfg
    cache = zustand["leck"].setdefault(f"{modell}|{pid}", {})
    k = f"{sz['key']}|{md5(hinweis)}"
    if k not in cache:
        roh = hd.llm(modell, pruefer_prompt(pid, sz, hinweis),
                     {"temperature": 0, "seed": 42, "num_predict": 450 if pid == "C1" else 160})
        cache[k] = parse_pruefer(roh)
    return cache[k]


# --------------------------------------------------------------------------------- Kennzahlen
def kappa(a, b, gewichtet=False, stufen=3):
    n = len(a)
    if n == 0:
        return float("nan")
    o = [[0] * stufen for _ in range(stufen)]
    for x, y in zip(a, b):
        o[x][y] += 1
    ra = [sum(o[i]) for i in range(stufen)]
    cb = [sum(o[i][j] for i in range(stufen)) for j in range(stufen)]
    num = den = 0.0
    for i in range(stufen):
        for j in range(stufen):
            w = ((i - j) ** 2 / (stufen - 1) ** 2) if gewichtet else (0 if i == j else 1)
            num += w * o[i][j] / n
            den += w * ra[i] * cb[j] / n ** 2
    return 1 - num / den if den else float("nan")


def kalibrierung_kennzahlen(cache, sz_liste):
    ref, pr = [], []
    ungueltig = 0
    for sz in sz_liste:
        r = REFERENZ_P1.get(sz["key"])
        if not r or r[1] != md5(sz["hinweis_b"]):
            continue
        u = cache.get(f"{sz['key']}|{md5(sz['hinweis_b'])}", {}).get("urteil", "")
        if u not in LECK_STUFE:
            ungueltig += 1
            continue
        ref.append(KLEIN[r[0]])
        pr.append(LECK_STUFE[u])
    n = len(ref)
    if n < 3:
        return {"n": n, "ungueltig": ungueltig, "kappa_bin": float("nan"), "kappa_w": float("nan"), "f1": 0.0,
                "recall": 0.0, "praez": 0.0, "treffer": 0.0}
    rb = [1 if x == 0 else 0 for x in ref]
    pb = [1 if x == 0 else 0 for x in pr]
    tp = sum(1 for x, y in zip(rb, pb) if x and y)
    fp = sum(1 for x, y in zip(rb, pb) if not x and y)
    fn = sum(1 for x, y in zip(rb, pb) if x and not y)
    praez = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {"n": n, "ungueltig": ungueltig, "kappa_bin": kappa(rb, pb, stufen=2), "kappa_w": kappa(ref, pr, True),
            "f1": 2 * praez * recall / (praez + recall) if praez + recall else 0.0, "recall": recall, "praez": praez,
            "treffer": sum(1 for x, y in zip(ref, pr) if x == y) / n}


def saetze(text):
    return [x for x in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if x]


JA_NEIN = re.compile(r"(?i)^(hast|hat|ist|sind|war|waren|kannst|kann|weißt|denkst|gibt|musst|muss|würde|wäre|siehst|überlegst)\b")
ERFUNDEN = re.compile(r"(?i)\bdu\s+(hast|habst)\s+(\w+\s+){0,2}(gesehen|gelernt|gelesen|erkannt|gehört)|\bdir\s+sicher\b|\bdu\s+weißt,?\s+dass\b")


def objektiv(sz, hinweis):
    s, n = sz["s"], sz["n"]
    saz = saetze(hinweis)
    frage_sz = [x for x in saz if x.endswith("?")]
    frueher = [t["hinweis"] for t in s["turns"][:n - 1]]
    h_w = hd.inhaltswoerter(hinweis)
    wiederh = 0.0
    for f in frueher:
        f_w = hd.inhaltswoerter(f)
        if h_w and f_w:
            wiederh = max(wiederh, len(h_w & f_w) / len(h_w | f_w))
    bezug = ""
    if n > 1:
        a_w = hd.inhaltswoerter(s["turns"][n - 2]["antwort"])
        bezug = bool(a_w & h_w) or bool(re.search(r"(?i)\bdu (schreibst|sagst|meinst|nennst|hast .{0,40}(geschrieben|genannt|gesagt))", hinweis))
    return {"zahlleck": bool(rp.hinweis_verraet_zahl(s["frage"], hinweis, s["loesung"])),
            "loesungswortanteil": hd.loesungswort_anteil(hinweis, s["loesung"], s["frage"]),
            "saetze": len(saz), "zu_lang": len(saz) > 3 or len(hinweis) > 420,
            "endet_frage": hinweis.strip().endswith("?"), "ja_nein": bool(frage_sz) and bool(JA_NEIN.match(frage_sz[0].strip())),
            "material": bool(rp.verweist_auf_material(hinweis, True, True)), "erfunden": bool(ERFUNDEN.search(hinweis)),
            "wiederholung": wiederh >= 0.6, "bezug_antwort": bezug}


def vorzeichentest(besser, schlechter):
    n = besser + schlechter
    if n == 0:
        return 1.0
    k = max(besser, schlechter)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n)


# ------------------------------------------------------------------------------------- Phasen
def phase1(args, zustand, sz_liste, pfad, t0, verfuegbar):
    konf = []
    for modell in [args.richter, args.lerner, rp.MODEL_NAME]:
        if modell in verfuegbar:
            konf += [(modell, "C1"), (modell, "C2")]
    ref_sz = [sz for sz in sz_liste if sz["key"] in REFERENZ_P1]
    if not ref_sz:
        raise SystemExit("Keine Situation mit Referenzurteil im Zustand gefunden (falscher Dialogtest?).")
    passend = sum(1 for sz in ref_sz if REFERENZ_P1[sz["key"]][1] == md5(sz["hinweis_b"]))
    if passend < 0.9 * len(ref_sz):
        print(f"WARNUNG: nur {passend}/{len(ref_sz)} Hinweise stimmen mit der Referenz überein; Kalibrierung eingeschränkt.")
    stunde = hd.stunde
    stunde(t0, f"Phase 1/4: Kalibrierung der Leck-Prüfer ({len(konf)} Konfigurationen x {len(ref_sz)} Hinweise)")
    ergebnisse = {}
    for cfg in konf:
        for i, sz in enumerate(ref_sz, 1):
            if REFERENZ_P1[sz["key"]][1] != md5(sz["hinweis_b"]):
                continue
            leck_pruefung(cfg, sz, sz["hinweis_b"], zustand)
            if i % 20 == 0:
                hd.speichere(zustand, pfad)
        hd.speichere(zustand, pfad)
        m = kalibrierung_kennzahlen(zustand["leck"][f"{cfg[0]}|{cfg[1]}"], ref_sz)
        ergebnisse[f"{cfg[0]}|{cfg[1]}"] = m
        print(f"  {cfg[0]:<18} {cfg[1]}  n={m['n']:<3} ungültig={m['ungueltig']:<3} kappa(Leck ja/nein)={m['kappa_bin']:.2f} "
              f"kappa_w={m['kappa_w']:.2f} Recall={m['recall']:.2f} Präzision={m['praez']:.2f} Treffer={m['treffer']:.0%}", flush=True)
    zustand["kalibrierung"] = ergebnisse

    def beste(modelle):
        kand = [(k, v) for k, v in ergebnisse.items() if k.split("|")[0] in modelle and v["n"] >= 3 and
                v["ungueltig"] <= 0.1 * max(1, v["n"] + v["ungueltig"])]
        if not kand:
            kand = [(k, v) for k, v in ergebnisse.items() if k.split("|")[0] in modelle]
        if not kand:
            return None
        kand.sort(key=lambda kv: (-(kv[1]["kappa_bin"] if kv[1]["kappa_bin"] == kv[1]["kappa_bin"] else -9), -kv[1]["recall"]))
        m, p = kand[0][0].split("|")
        return (m, p)
    unabh = [m for m in (args.richter, args.lerner) if m in verfuegbar]
    zustand["pruefer_eval"] = beste(unabh)
    zustand["pruefer_waechter"] = beste([rp.MODEL_NAME]) or zustand["pruefer_eval"]
    for rolle in ("pruefer_eval", "pruefer_waechter"):
        c = zustand[rolle]
        k = ergebnisse.get(f"{c[0]}|{c[1]}", {}) if c else {}
        print(f"  gewählt {rolle}: {c}  kappa(Leck ja/nein) = {k.get('kappa_bin', float('nan')):.2f}")
    # lexikalischer Vergleich
    rb = [1 if REFERENZ_P1[sz['key']][0] == 'n' else 0 for sz in ref_sz]
    for schw in (0.2, 0.3, 0.4):
        pb = [1 if hd.loesungswort_anteil(sz['hinweis_b'], sz['s']['loesung'], sz['s']['frage']) >= schw else 0 for sz in ref_sz]
        print(f"  Vergleich Wortanteil >= {schw}: kappa(Leck ja/nein) = {kappa(rb, pb, stufen=2):.2f}")
    hd.speichere(zustand, pfad)


def phase2(args, zustand, sz_liste, pfad, t0):
    hd.stunde(t0, f"Phase 2/4: Erzeugung der Varianten V1-V3 ({len(sz_liste)} Situationen)")
    gen = zustand["gen"]
    waechter_cfg = tuple(zustand["pruefer_waechter"])
    zustand.setdefault("repro", {})

    def mit_waechter(sz, start, fn_prompt):
        hinweis, hp = start
        retries = 0
        verlauf = []
        urt = leck_pruefung(waechter_cfg, sz, hinweis, zustand)
        while urt["urteil"] == "leck" and retries < args.max_neu:
            retries += 1
            verlauf.append(urt["genannt"])
            zusatz = (f"\n\nACHTUNG: Dein letzter Entwurf war:\n\"{hinweis}\"\nEr verrät laut Prüfung: {urt['genannt'] or 'einen Baustein der Lösung'}. "
                      f"Schreibe einen neuen Hinweis als engere Frage, die das weder nennt noch umschreibt noch als Auswahl anbietet.")
            neu, hp2 = erzeuge(fn_prompt(sz) + zusatz, sz["s"])
            if not neu:
                break
            hinweis, hp = neu, hp2
            urt = leck_pruefung(waechter_cfg, sz, hinweis, zustand)
        ersatz = urt["urteil"] == "leck"
        if ersatz:
            hinweis, hp = ERSATZ_HINWEIS, "waechter_ersatz"
        return hinweis, hp, retries, ersatz

    for i, sz in enumerate(sz_liste, 1):
        k = sz["key"]
        z0 = time.time()
        # V2: neuer Prompt
        if k not in gen["V2"]:
            h, hp = erzeuge(prompt_neu(sz), sz["s"])
            gen["V2"][k] = {"hinweis": h or sz["hinweis_b"], "pruefung": hp if h else "format_fehler_basis"}
        # V1: Basis + Wächter (Start = gespeicherter Basis-Hinweis)
        if k not in gen["V1"]:
            h, hp, r, e = mit_waechter(sz, (sz["hinweis_b"], sz["s"]["turns"][sz["n"] - 1].get("hinweis_pruefung", "")), prompt_basis)
            gen["V1"][k] = {"hinweis": h, "pruefung": hp, "retries": r, "ersatz": e}
        # V3: H-v4 + Wächter
        if k not in gen["V3"]:
            h, hp, r, e = mit_waechter(sz, (gen["V2"][k]["hinweis"], gen["V2"][k]["pruefung"]), prompt_neu)
            gen["V3"][k] = {"hinweis": h, "pruefung": hp, "retries": r, "ersatz": e}
        # Reproduzierbarkeit der Basis (die ersten 8): Erzeugung erneut, Vergleich mit gespeichertem Hinweis
        if len(zustand["repro"]) < 8 and k not in zustand["repro"]:
            h, _ = erzeuge(prompt_basis(sz), sz["s"])
            zustand["repro"][k] = (h.strip() == sz["hinweis_b"].strip())
        if i % 5 == 0 or i == len(sz_liste):
            hd.speichere(zustand, pfad)
            print(f"  [{i}/{len(sz_liste)}] {k:<8} {time.time() - z0:.0f}s  V1 neu={gen['V1'][k]['retries']} ersatz={gen['V1'][k]['ersatz']}  "
                  f"V3 neu={gen['V3'][k]['retries']} ersatz={gen['V3'][k]['ersatz']}", flush=True)
    hd.speichere(zustand, pfad)
    if zustand["repro"]:
        print(f"  Reproduzierbarkeit der Basis: {sum(zustand['repro'].values())}/{len(zustand['repro'])} gleich")


def hinweis_von(zustand, sz, v):
    return sz["hinweis_b"] if v == "B" else zustand["gen"][v][sz["key"]]["hinweis"]


def phase3(args, zustand, sz_liste, pfad, t0):
    eval_cfg = tuple(zustand["pruefer_eval"])
    hd.stunde(t0, f"Phase 3/4: Auswertung ({eval_cfg[0]}/{eval_cfg[1]} als unabhängiger Leck-Prüfer, Rubrik durch {args.richter})")
    for v in VARIANTEN:
        for i, sz in enumerate(sz_liste, 1):
            leck_pruefung(eval_cfg, sz, hinweis_von(zustand, sz, v), zustand)
            if i % 25 == 0:
                hd.speichere(zustand, pfad)
        hd.speichere(zustand, pfad)
        print(f"  Leck-Prüfung {v} fertig", flush=True)
    zustand.setdefault("rubrik", {})
    todo = [(v, sz) for v in VARIANTEN if v != "B" for sz in sz_liste if f"{v}|{sz['key']}" not in zustand["rubrik"]]
    hd.stunde(t0, f"  Rubrik P1-P6 ({len(todo)} Hinweise, {args.richter})")
    for i, (v, sz) in enumerate(todo, 1):
        t = {"n": sz["n"], "hinweis": hinweis_von(zustand, sz, v)}
        roh = hd.llm(args.richter, hd.judge_prompt("hinweis", sz["s"], t, t["hinweis"]), {"temperature": 0, "seed": 42, "num_predict": 400})
        zustand["rubrik"][f"{v}|{sz['key']}"] = hd.parse_judge(roh, hd.HINWEIS_ITEMS)
        if i % 20 == 0 or i == len(todo):
            hd.speichere(zustand, pfad)
            print(f"  [{i}/{len(todo)}] bewertet", flush=True)
    hd.speichere(zustand, pfad)


def rubrik_von(zustand, sz, v):
    if v == "B":
        b = sz["urteile_b"]
        return {k: b.get(k, "") for k in hd.HINWEIS_ITEMS}
    return zustand["rubrik"].get(f"{v}|{sz['key']}", {})


def tabelle_zeilen(zustand, sz_liste):
    eval_cfg = tuple(zustand["pruefer_eval"])
    cache = zustand["leck"][f"{eval_cfg[0]}|{eval_cfg[1]}"]
    zeilen = []
    for sz in sz_liste:
        z = {"id": sz["s"]["id"], "versuch": sz["n"], "frage": sz["s"]["frage"], "loesung": sz["s"]["loesung"],
             "letzte_antwort": sz["s"]["turns"][sz["n"] - 2]["antwort"] if sz["n"] > 1 else ""}
        for v in VARIANTEN:
            h = hinweis_von(zustand, sz, v)
            lp = cache.get(f"{sz['key']}|{md5(h)}", {})
            ob = objektiv(sz, h)
            ru = rubrik_von(zustand, sz, v)
            g = zustand["gen"].get(v, {}).get(sz["key"], {})
            z.update({f"{v}_hinweis": h, f"{v}_leck": lp.get("urteil", ""), f"{v}_genannt": lp.get("genannt", ""),
                      f"{v}_retries": g.get("retries", ""), f"{v}_ersatz": g.get("ersatz", ""),
                      f"{v}_ref_P1": REFERENZ_P1.get(sz["key"], ("", ""))[0] if v == "B" else ""})
            z.update({f"{v}_ob_{k}": val for k, val in ob.items()})
            z.update({f"{v}_J_{k}": ru.get(k, "") for k in hd.HINWEIS_ITEMS})
        zeilen.append(z)
    return zeilen


def bogen(args, zustand, sz_liste, basis_pfad):
    rnd = random.Random(args.seed + 11)
    quoten = {1: 12, 2: 8, 3: 4}
    objekte = []
    gewaehlt = []
    for n, q in quoten.items():
        pool = [sz for sz in sz_liste if sz["n"] == n]
        gewaehlt += rnd.sample(pool, min(q, len(pool)))
    for sz in gewaehlt:
        texte = defaultdict(list)
        for v in VARIANTEN:
            texte[hinweis_von(zustand, sz, v).strip()].append(v)
        for text, vs in texte.items():
            objekte.append((sz, text, vs))
    rnd.shuffle(objekte)
    zeilen, schluessel = [], []
    for nr, (sz, text, vs) in enumerate(objekte, 1):
        s, n = sz["s"], sz["n"]
        z = {"bogen_nr": nr, "frage": s["frage"], "loesung_referenz": s["loesung"],
             "verlauf_davor": hd.verlauf_text(s, n - 1) if n > 1 else "", "zu_bewerten": text}
        for r in ("R1", "R2"):
            for k in hd.HINWEIS_ITEMS:
                z[f"{r}_{k}"] = ""
        zeilen.append(z)
        schluessel.append({"bogen_nr": nr, "situation": sz["key"], "varianten": "+".join(vs)})
    felder = ["bogen_nr", "frage", "loesung_referenz", "verlauf_davor", "zu_bewerten"] + [f"{r}_{k}" for r in ("R1", "R2") for k in hd.HINWEIS_ITEMS]
    hd.schreibe_csv(f"{basis_pfad}_bewertungsbogen.csv", felder, zeilen)
    hd.schreibe_csv(f"{basis_pfad}_bogen_schluessel.csv", ["bogen_nr", "situation", "varianten"], schluessel)
    legende = ["Bewertungsbogen Hinweise: je Zeile ein Hinweis (verblindet, Reihenfolge gemischt). Bewerten mit P1-P6, Werte ja / teilweise / nein; "
               "zwei Personen getrennt, ohne Absprache. Schlüssel (welche Variante) erst nach beiden Bewertungen öffnen.", "",
               "Operationale Fassung P1: ja = der Hinweis nennt keinen Baustein der Lösung, der nicht schon in der Frage oder in den Antworten der Person steht "
               "(weder wörtlich noch umschrieben, nicht als Definition, nicht als richtige Option einer Entweder-oder-Frage, nicht als Aussage, der man nur "
               "zustimmen muss); teilweise = nur ein Randbegriff oder ein kleiner Teil; nein = ein zentraler Baustein wird genannt.", ""]
    legende += [f"{k}  {v}" for k, v in hd.HINWEIS_ITEMS.items()]
    Path(f"{basis_pfad}_legende.txt").write_text("\n".join(legende), encoding="utf-8")
    return [f"{basis_pfad}_bewertungsbogen.csv", f"{basis_pfad}_bogen_schluessel.csv", f"{basis_pfad}_legende.txt"], len(zeilen)


def prozent(x, n):
    return f"{100 * x / n:.0f}%" if n else "-"


def ausgabe(args, zustand, sz_liste, label, t0, rauch):
    basis = f"evaluationsdaten/hinweis_opt_{label}"
    zeilen = tabelle_zeilen(zustand, sz_liste)
    felder = list(zeilen[0].keys())
    hd.schreibe_csv(f"{basis}_varianten.csv", felder, zeilen)
    eval_cfg = zustand["pruefer_eval"]
    wcfg = zustand["pruefer_waechter"]
    kal = zustand.get("kalibrierung", {})
    ke = kal.get(f"{eval_cfg[0]}|{eval_cfg[1]}", {})
    L = [f"Hinweis-Optimierung {label} ({VERSION}, Prompt {PROMPT_NEU})  {datetime.datetime.now():%d.%m.%Y %H:%M}",
         f"Replay von {len(sz_liste)} Hinweis-Situationen aus {BASIS_LABEL} (Versuch 1: {sum(1 for s in sz_liste if s['n'] == 1)}, "
         f"Versuch 2: {sum(1 for s in sz_liste if s['n'] == 2)}, Versuch 3: {sum(1 for s in sz_liste if s['n'] == 3)}); Generator {rp.MODEL_NAME} (T=0, Seed 42)",
         f"Leck-Prüfer Auswertung (unabhängig): {eval_cfg[0]} / {eval_cfg[1]}  kappa(Leck ja/nein) gegen Referenz = {ke.get('kappa_bin', float('nan')):.2f}, "
         f"kappa_w = {ke.get('kappa_w', float('nan')):.2f}, Recall = {ke.get('recall', 0):.2f}",
         f"Leck-Prüfer Wächter ({rp.MODEL_NAME}): {wcfg[0]} / {wcfg[1]}  kappa = {kal.get(wcfg[0] + '|' + wcfg[1], {}).get('kappa_bin', float('nan')):.2f}",
         ""]
    schwach = ke.get("kappa_bin", 0) != ke.get("kappa_bin", 0) or ke.get("kappa_bin", 0) < 0.4
    if schwach:
        L.append("HINWEIS: Der Leck-Prüfer erreicht gegen die Referenz kein kappa >= 0.4. Die Leck-Raten unten sind nur Orientierung; "
                 "die Entscheidung stützt sich auf den Bewertungsbogen (zwei Menschen).")
        L.append("")
    L.append("Kalibrierung aller Prüfer (kappa Leck ja/nein | kappa_w | Recall | Präzision):")
    for k, v in kal.items():
        L.append(f"  {k:<28} n={v['n']:<3} {v['kappa_bin']:.2f} | {v['kappa_w']:.2f} | {v['recall']:.2f} | {v['praez']:.2f}")
    L.append("")
    L.append("Leck-Rate laut unabhängigem Prüfer (leck / teilweise / kein_leck) je Variante und Versuch:")
    L.append(f"{'':<5}{'Variante':<22}" + "".join(f"{'Versuch ' + str(v):>26}" for v in (1, 2, 3)) + f"{'gesamt':>26}")
    kennzahl = {}
    for v in VARIANTEN:
        teile = []
        for sel in ((1,), (2,), (3,), (1, 2, 3)):
            zs = [z for z in zeilen if z["versuch"] in sel and z[f"{v}_leck"]]
            n = len(zs)
            c = Counter(z[f"{v}_leck"] for z in zs)
            teile.append(f"{prozent(c['leck'], n):>6}/{prozent(c['teilweise'], n):>5}/{prozent(c['kein_leck'], n):>5} (n={n})")
            if sel == (1, 2, 3):
                kennzahl[v] = c["leck"] / n if n else 1.0
        L.append(f"     {v + ' ' + BESCHREIBUNG[v]:<22}" + "".join(f"{t:>26}" for t in teile))
    L.append("")
    L.append("Gepaarter Vergleich mit der Basis (Leck laut Prüfer; besser = Basis Leck, Variante nicht; Vorzeichentest zweiseitig):")
    for v in VARIANTEN[1:]:
        b = sum(1 for z in zeilen if z["B_leck"] == "leck" and z[f"{v}_leck"] and z[f"{v}_leck"] != "leck")
        s = sum(1 for z in zeilen if z["B_leck"] and z["B_leck"] != "leck" and z[f"{v}_leck"] == "leck")
        L.append(f"  {v}: besser {b}, schlechter {s}, p = {vorzeichentest(b, s):.3f}")
    L.append("")
    L.append("Objektive Kennzahlen (Anteil der Hinweise; ohne Modell):")
    kopf = ["zahlleck", "zu_lang", "endet_frage", "ja_nein", "material", "erfunden", "wiederholung"]
    L.append(f"{'':<5}{'Variante':<22}" + "".join(f"{k:>13}" for k in kopf) + f"{'Wortanteil':>12}{'Bezug(V>=2)':>13}")
    objekt_ok = {}
    for v in VARIANTEN:
        n = len(zeilen)
        zv2 = [z for z in zeilen if z["versuch"] >= 2]
        werte = {k: sum(1 for z in zeilen if z[f"{v}_ob_{k}"]) for k in kopf}
        objekt_ok[v] = werte
        wa = sum(float(z[f"{v}_ob_loesungswortanteil"]) for z in zeilen) / n
        bz = sum(1 for z in zv2 if z[f"{v}_ob_bezug_antwort"])
        L.append(f"     {v + ' ' + BESCHREIBUNG[v]:<22}" + "".join(f"{prozent(werte[k], n):>13}" for k in kopf) + f"{wa:>12.2f}{prozent(bz, len(zv2)):>13}")
    L.append("")
    L.append("Wächter: " + "; ".join(f"{v}: Neufassungen im Mittel "
                                    f"{sum(zustand['gen'][v][sz['key']]['retries'] for sz in sz_liste) / len(sz_liste):.2f}, Ersatzhinweis "
                                    f"{sum(1 for sz in sz_liste if zustand['gen'][v][sz['key']]['ersatz'])}x" for v in ('V1', 'V3')))
    L.append("")
    L.append(f"Rubrik durch {args.richter} (Anteil ja; nur ergänzend, P1 des Richters war in HD-V2 nicht belastbar):")
    L.append(f"{'':<5}{'Variante':<22}" + "".join(f"{k:>8}" for k in hd.HINWEIS_ITEMS))
    for v in VARIANTEN:
        n = len(zeilen)
        L.append(f"     {v + ' ' + BESCHREIBUNG[v]:<22}" + "".join(f"{prozent(sum(1 for z in zeilen if z[f'{v}_J_{k}'] == 'ja'), n):>8}" for k in hd.HINWEIS_ITEMS))
    L.append("")
    # Empfehlung
    kand = []
    for v in VARIANTEN:
        sch = objekt_ok[v]["material"] + objekt_ok[v]["erfunden"] + objekt_ok[v]["wiederholung"] + objekt_ok[v]["zu_lang"]
        sch_b = objekt_ok["B"]["material"] + objekt_ok["B"]["erfunden"] + objekt_ok["B"]["wiederholung"] + objekt_ok["B"]["zu_lang"]
        ersatz_quote = (sum(1 for sz in sz_liste if zustand["gen"].get(v, {}).get(sz["key"], {}).get("ersatz")) / len(sz_liste)) if v != "B" else 0.0
        if sch <= sch_b + 0.05 * len(zeilen) and ersatz_quote <= 0.10:
            kand.append(v)
    kand.sort(key=lambda v: (round(kennzahl[v], 2), VARIANTEN.index(v)))
    beste = kand[0]
    einfach = next(v for v in VARIANTEN if v in kand and kennzahl[v] <= kennzahl[beste] + 0.03)
    L.append(f"Vorläufige Empfehlung nach Leck-Rate (nur wenn Material/erfundener Kontext/Wiederholung/Länge nicht um mehr als 5 Prozentpunkte "
             f"schlechter als die Basis und höchstens 10 % Ersatzhinweise; bei Gleichstand bis 3 Prozentpunkte die einfachere Variante): {einfach} ({BESCHREIBUNG[einfach]}).")
    L.append("Das ist ein Entwicklungsbefund. Verbindlich ist erst der Bewertungsbogen (zwei Menschen) und ein einmaliger Lauf der eingefrorenen Variante auf einem Held-out-Satz.")
    L.append("")
    if zustand.get("repro"):
        L.append(f"Reproduzierbarkeit: Basis-Hinweise bei erneuter Erzeugung gleich: {sum(zustand['repro'].values())}/{len(zustand['repro'])}.")
    L += ["Grenzen: Replay mit festen früheren Verläufen; Entwicklungsdaten (N100 kein Held-out); Leck-Prüfer an einem Satz Referenzurteile kalibriert (nur Basis-Hinweise);",
          "keine echten Lernenden; kein Beleg für Lernwirkung. P2-P6 der Varianten sind nur objektiv/durch den Richter erfasst.",
          f"Gesamtdauer: {(time.time() - t0) / 60:.0f} min"]
    Path(f"{basis}_zusammenfassung.txt").write_text("\n".join(L), encoding="utf-8")
    print("\n" + "\n".join(L))
    dateien = [f"{basis}_varianten.csv", f"{basis}_zusammenfassung.txt"]
    if not rauch:
        d2, n_bogen = bogen(args, zustand, sz_liste, basis)
        dateien += d2
        print(f"Bewertungsbogen: {n_bogen} Hinweise (verblindet), Schlüssel getrennt.")
    return dateien, einfach


def doku_und_git(label, dateien, einfach):
    text = (f"Hinweis-Optimierung {label} ({datetime.date.today():%d %b %Y}): Replay der 143 Hinweis-Situationen aus {BASIS_LABEL}; "
            f"Varianten Basis, Wächter (Leck-Prüfer mit Neufassung), Prompt {PROMPT_NEU} (Lösungsbausteine, ein Ziel, Formregeln P1-P6) und Kombination; "
            f"Leck-Prüfer vorher gegen Referenzurteile kalibriert. Vorläufige Empfehlung nach Leck-Rate: {einfach}. "
            f"Skript skripte/evaluation/optimiere_hinweise.py; Ergebnisse evaluationsdaten/hinweis_opt_{label}_*. "
            f"Entwicklungsbefund, kein Beleg im Beitrag; Bewertungsbogen für zwei Menschen liegt bei.")
    marke = f"## Hinweis-Optimierung {label}"
    for f in ("README.md", *glob.glob("PROZESSABLAUF.md"), *glob.glob("doku/PROZESSABLAUF.md"), *glob.glob("docs/PROZESSABLAUF.md")):
        p = Path(f)
        if p.exists() and marke not in p.read_text(encoding="utf-8"):
            with open(p, "a", encoding="utf-8") as fh:
                fh.write(f"\n{marke}\n{text}\n")
            print(f"{f}: Abschnitt angehängt.")
    if Path(".git").is_dir():
        subprocess.run(["git", "add", "-A"], check=False)
        r = subprocess.run(["git", "commit", "-q", "-m", f"Hinweis-Optimierung {label}: Skript und Ergebnisse"], check=False)
        print("Commit angelegt." if r.returncode == 0 else "Nichts zu committen.")
    for d in glob.glob("/mnt/c/Users/*/Downloads"):
        if any(x in d for x in ("Public", "Default", "All Users")):
            continue
        for f in dateien:
            try:
                shutil.copy2(f, d)
            except OSError:
                pass
        print(f"Kopien in {d}")
        break


def lauf(args, label, sz_liste, rauch, verfuegbar, t0):
    pfad = Path(f"evaluationsdaten/hinweis_opt_{label}_zustand.json")
    if pfad.exists():
        zustand = json.loads(pfad.read_text(encoding="utf-8"))
        print(f"Fortsetzung aus {pfad}")
    else:
        zustand = {}
    zustand.setdefault("leck", {})
    zustand.setdefault("gen", {v: {} for v in VARIANTEN[1:]})
    for v in VARIANTEN[1:]:
        zustand["gen"].setdefault(v, {})
    zustand.setdefault("rubrik", {})
    phase1(args, zustand, sz_liste, pfad, t0, verfuegbar)
    phase2(args, zustand, sz_liste, pfad, t0)
    phase3(args, zustand, sz_liste, pfad, t0)
    return ausgabe(args, zustand, sz_liste, label, t0, rauch)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="HO-V1")
    ap.add_argument("--basis", default=BASIS_LABEL, help="Label des Dialogtests, dessen Situationen wiedergegeben werden")
    ap.add_argument("--richter", default="mistral-nemo")
    ap.add_argument("--lerner", default="granite4.1:8b", help="zweites unabhängiges Modell für den Leck-Prüfer (fehlt es, wird es übersprungen)")
    ap.add_argument("--max-neu", type=int, default=2, help="Neufassungen je Hinweis im Wächter")
    ap.add_argument("--limit", type=int, default=0, help="nur so viele Situationen (Test)")
    ap.add_argument("--ohne-rauchtest", action="store_true")
    ap.add_argument("--seed", type=int, default=2028)
    args = ap.parse_args()
    t0 = time.time()
    if rp.MODEL_NAME in (args.richter, args.lerner):
        raise SystemExit("ABBRUCH: Richter und zweiter Prüfer dürfen nicht das Generatormodell sein.")
    hd.pruefe_modelle(rp.MODEL_NAME, args.richter)
    try:
        import requests
        tags = requests.get(rp.OLLAMA_URL.replace("/api/generate", "/api/tags"), timeout=20).json().get("models", [])
        namen = [m["name"] for m in tags]
    except Exception:
        namen = []
    def da(n):
        return any(v == n or v.split(":")[0] == n or v.startswith(n + ":") for v in namen)
    verfuegbar = {m for m in (rp.MODEL_NAME, args.richter, args.lerner) if da(m)}
    if args.lerner not in verfuegbar:
        print(f"HINWEIS: {args.lerner} nicht installiert; zweiter unabhängiger Prüfer entfällt.")
    rp.RRF_K = 5
    Path("evaluationsdaten").mkdir(exist_ok=True)
    alle = lade_szenarien(args.basis)
    print(f"{len(alle)} Hinweis-Situationen aus {args.basis} (Versuch 1: {sum(1 for s in alle if s['n'] == 1)}, "
          f"2: {sum(1 for s in alle if s['n'] == 2)}, 3: {sum(1 for s in alle if s['n'] == 3)}); Konfiguration: "
          f"{ {k: v for k, v in sorted(__import__('os').environ.items()) if k.startswith('LERNASSISTENT_')} }")
    if args.limit:
        alle = alle[:args.limit]
    if Path(".git").is_dir() and not Path(f"evaluationsdaten/hinweis_opt_{args.label}_zustand.json").exists():
        subprocess.run(["git", "add", "-A"], check=False)
        subprocess.run(["git", "commit", "-q", "-m", "Stand vor Hinweis-Optimierung"], check=False)
        subprocess.run(["git", "tag", "vor-hinweisoptimierung"], check=False, stderr=subprocess.DEVNULL)
    if not args.ohne_rauchtest and not args.limit:
        auswahl = []
        for n in (1, 1, 2):
            kand = [sz for sz in alle if sz["n"] == n and sz not in auswahl and sz["key"] in REFERENZ_P1]
            if kand:
                auswahl.append(kand[len(auswahl) * 7 % len(kand)])
        hd.stunde(t0, f"Rauchtest mit {len(auswahl)} Situationen (alle Phasen, Label {args.label}-RAUCH)")
        try:
            lauf(args, args.label + "-RAUCH", auswahl, True, verfuegbar, t0)
        except Exception as e:  # noqa: BLE001
            raise SystemExit(f"ABBRUCH im Rauchtest: {type(e).__name__}: {e}\nNichts weiter gelaufen. Meldung an die Entwicklung weitergeben.")
        hd.stunde(t0, "Rauchtest bestanden, voller Lauf beginnt (ca. 5-7 h)")
    label = args.label + ("-TEST" if args.limit else "")
    dateien, einfach = lauf(args, label, alle, bool(args.limit), verfuegbar, t0)
    if not args.limit:
        doku_und_git(label, dateien, einfach)
    hd.stunde(t0, "Fertig")


if __name__ == "__main__":
    main()

"""
teste_v10_offline.py
--------------------
Offline-Tests für V10 (RP-v2, HP-v4/FP-v3, G-v4, IF-v5) ohne Ollama:
  1. konstruierte Fälle für RP-v2 (Konsistenz, sichtbare Überlegung) und die neuen Materialmuster;
  2. Ablauf von rechnung_pruefen mit simuliertem Modell (nachgebessert / markiert / nicht_behoben, RP-v1 unverändert);
  3. echte Modelltexte aus früheren Läufen: welche Lösungen RP-v2 meldet, welche Hinweise/Rückmeldungen
     die neuen Materialmuster melden (erwartet: nur die bekannten Fälle).

Aufruf (aus dem Projektordner):
  python skripte/evaluation/teste_v10_offline.py
  python skripte/evaluation/teste_v10_offline.py --vergleich evaluationsdaten/vergleich_rag_RAGVGL-V9D.csv \
      --ideen evaluationsdaten/ideen_test_V9D-IDEEN.csv
"""
import sys as _sys, pathlib as _pl  # Projektpfade (lernassistent/pfadsetup.py)
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401

import argparse
import csv
import os

import rag_pipeline as rp
import rechenpruefung as rc

FEHLER = []


def pruefe(bedingung, text):
    print(("  ok   " if bedingung else "  FEHLER ") + text)
    if not bedingung:
        FEHLER.append(text)


def konstruierte_faelle():
    print("1a. RP-v2 (konstruiert)")
    faelle = [
        ("Der Schlupf beträgt 0,02 oder 2 %. Es gilt s = (1500 - 1425) / 1500 = 75 / 1500 = 0,05.",
         "n = 1425 1/min, n_s = 1500 1/min", True),
        ("Der Schlupf beträgt 5 %. Es gilt s = (1500 - 1425) / 1500 = 75 / 1500 = 0,05.",
         "n = 1425 1/min, n_s = 1500 1/min", False),
        ("Der Strom beträgt ca. 23 A. Das ergibt I = 4882 W / (√3 · 400 V · 0,81) ≈ 8,7 A.", "", True),
        ("Der Strom beträgt z. B. 8,7 A. Das ergibt I = 4882 W / (√3 · 400 V · 0,81) ≈ 8,7 A.", "", False),
        ("Der Wirkungsgrad beträgt 81,9 %. η = 4000 W / 4882 W = 0,819 = 81,9 %.", "", False),
        ("Die Temperatur beträgt 255 °C. (150 K/W · 1,5 W + 30 °C = 255 °C).", "", False),
        ("Bei einem DMM beträgt Ri mindestens 10 MΩ, z. B. bei I = 2 A.", "", False),
        ("Die Leistung beträgt 4,882 kW. P = √3 · 400 V · 8,7 A · 0,81 = 4882 W.", "", False),
        ("Das Drehmoment beträgt 95,5 Nm. Das Moment ergibt sich aus M = 9550 · 10 / 1000 = 95,5 Nm.", "", False),
        ("Der Wert muss bei Abweichung von 20 °C korrigiert werden. Der Korrekturfaktor beträgt 0,8.", "", False),
        ("Momentan habe ich einen Rechenfehler gemacht; lass uns das korrigieren.", "", True),
        ("Warte, ich prüfe das. Die Spannung beträgt 400 V.", "", True),
        ("*Korrektur basierend auf L1:* Der Strom fehlt.", "", True),
        ("Entscheidung: STATUS: TEILWEISE. Der Strom fehlt.", "", True),
    ]
    for text, frage, erwartet in faelle:
        b = rc.pruefe(text, frage)
        pruefe(bool(b) == erwartet, f"{'meldet' if erwartet else 'still '} | {text[:70]}")
    pruefe(rc.pruefe("Der Schlupf beträgt 0,02 oder 2 %. s = 75 / 1500 = 0,05.", "", "RP-v1") == [],
           "RP-v1 meldet Konsistenzfehler nicht (unverändert)")

    print("1b. Materialmuster V10 (konstruiert)")
    ja = ["Suche im bereitgestellten Material nach dem Eintrag für Aluminium.",
          "Wenn du in der Spannungsreihe nach dem Metall Zink suchst, was siehst du dann?",
          "Sieh im vorliegenden Text nach."]
    nein = ["Überlege, wonach du eigentlich suchst.", "Im vorliegenden Fall fließt kein Strom.",
            "Nach dem Einschalten steigt der Strom stark an.", "Untersuche, wie sich der Widerstand ändert.",
            "Versuche, die Formel umzustellen."]
    for t in ja:
        pruefe(bool(rp.verweist_auf_material(t)), f"meldet | {t}")
    for t in nein:
        pruefe(not rp.MATERIAL_VERWEIS_V10.search(t), f"still  | {t}")
    pruefe(not rp.verweist_auf_material(ja[0], v10=False) or "bereitgestellt" not in " ".join(
        rp.verweist_auf_material(ja[0], v10=False)), "v10=False (HP-v3/FP-v2) ohne neue Muster")


def ablauf_mit_simuliertem_modell():
    print("2. rechnung_pruefen mit simuliertem Modell")
    alt = rp.frage_llm, rp.SCAFFOLDING_VERSION, rp.RECHEN_PRUEFUNG_VERSION
    prompt = "…\n### Frage\nWie groß ist der Schlupf bei n = 1425 1/min und n_s = 1500 1/min?\n\nAntworte genau …"
    falsch = "Der Schlupf beträgt 0,02 oder 2 %. Es gilt s = (1500 - 1425) / 1500 = 75 / 1500 = 0,05."
    gut = "STATUS: BEANTWORTET\nLÖSUNG: Der Schlupf beträgt 0,05 oder 5 %. s = 75 / 1500 = 0,05.\nÜBERLEGUNG: x\nHINWEIS: Was bedeutet Schlupf?"
    schlecht = "STATUS: BEANTWORTET\nLÖSUNG: " + falsch + "\nÜBERLEGUNG: x\nHINWEIS: Was bedeutet Schlupf?"
    try:
        rp.SCAFFOLDING_VERSION, rp.RECHEN_PRUEFUNG_VERSION = "G-v4", "RP-v2"
        aufrufe = []
        rp.frage_llm = lambda p, **k: (aufrufe.append(p), gut)[1]
        st = rp.rechnung_pruefen(prompt, {"status": "BEANTWORTET", "loesung": falsch, "hinweis": "h"})
        pruefe(st["rechen_pruefung"] == "nachgebessert" and "0,05 oder 5 %" in st["loesung"], "nachgebessert")
        pruefe(len(aufrufe) == 1 and "ohne Zwischenüberlegungen" in aufrufe[0], "ein Aufruf, RP-v2-Prompt")
        rp.frage_llm = lambda p, **k: schlecht
        st = rp.rechnung_pruefen(prompt, {"status": "BEANTWORTET", "loesung": falsch, "hinweis": "h"})
        pruefe(st["rechen_pruefung"] == "markiert" and "⚠ Automatische Prüfung" in st["loesung"], "markiert mit Vermerk")
        nur_ueberlegung = "Die Spannung beträgt 400 V. Warte, das stimmt so."
        rp.frage_llm = lambda p, **k: "STATUS: BEANTWORTET\nLÖSUNG: " + nur_ueberlegung + "\nHINWEIS: h"
        st = rp.rechnung_pruefen(prompt, {"status": "BEANTWORTET", "loesung": nur_ueberlegung, "hinweis": "h"})
        pruefe(st["rechen_pruefung"] == "nicht_behoben" and st["loesung"] == nur_ueberlegung,
               "nur Überlegung: nicht_behoben, Lösung ohne Vermerk")
        rp.RECHEN_PRUEFUNG_VERSION = "RP-v1"
        rp.frage_llm = lambda p, **k: (_ for _ in ()).throw(AssertionError("kein Aufruf erwartet"))
        st = rp.rechnung_pruefen(prompt, {"status": "BEANTWORTET", "loesung": falsch, "hinweis": "h"})
        pruefe(st["rechen_pruefung"] == "ok", "RP-v1: Konsistenzfehler bleibt unbemerkt (wie V9d)")
    finally:
        rp.frage_llm, rp.SCAFFOLDING_VERSION, rp.RECHEN_PRUEFUNG_VERSION = alt

    print("2b. hinweis_pruefen mit simuliertem Modell (HP-v4 vs. HP-v3)")
    alt = rp.frage_llm, rp.SCAFFOLDING_VERSION, rp.HINWEIS_PRUEFUNG_VERSION
    hinweis = "Suche im bereitgestellten Material nach dem Eintrag für Aluminium."
    try:
        rp.SCAFFOLDING_VERSION = "G-v4"
        rp.frage_llm = lambda p, **k: "HINWEIS: Was beschreibt der spezifische Widerstand eines Stoffes?"
        for version, erwartet in (("HP-v4", "nachgebessert"), ("HP-v3", "ok")):
            rp.HINWEIS_PRUEFUNG_VERSION = version
            st = rp.hinweis_pruefen("Wie groß ist der spezifische Widerstand von Aluminium?",
                                    {"status": "BEANTWORTET", "hinweis": hinweis, "loesung": "0,02857 Ω mm²/m"})
            pruefe(st["hinweis_pruefung"] == erwartet, f"{version}: {erwartet}")
    finally:
        rp.frage_llm, rp.SCAFFOLDING_VERSION, rp.HINWEIS_PRUEFUNG_VERSION = alt


def echte_texte(vergleich, ideen):
    print("3. Echte Modelltexte früherer Läufe")
    loesungen, hinweise = {}, {}
    for pfad in vergleich:
        if not os.path.exists(pfad):
            print(f"  (fehlt: {pfad})")
            continue
        for z in csv.DictReader(open(pfad, encoding="utf-8-sig")):
            if z.get("status_mit") in ("BEANTWORTET", "TEILWEISE"):
                loesungen[(os.path.basename(pfad), z["nr"])] = (z["antwort_mit"], z["frage"])
    for pfad in ideen:
        if not os.path.exists(pfad):
            print(f"  (fehlt: {pfad})")
            continue
        for z in csv.DictReader(open(pfad, encoding="utf-8-sig")):
            if z.get("status") in ("BEANTWORTET", "TEILWEISE"):
                loesungen[(os.path.basename(pfad), z["frage_id"])] = (z["loesung"], z["frage"])
            for k in ("hinweis", "hinweis_original", "rueckmeldung", "rueckmeldung_original"):
                if (z.get(k) or "").strip():
                    hinweise[z[k].strip()] = (os.path.basename(pfad), z["frage_id"], k)
    print(f"  {len(loesungen)} Lösungen, {len(hinweise)} Hinweise/Rückmeldungen")
    for schluessel, (text, frage) in sorted(loesungen.items()):
        b = rc.pruefe(text, frage)
        if b:
            print(f"  RP-v2 meldet {schluessel}: " + " | ".join(f"{x.get('art', 'rechnung')}: {x['text'][:90]}" for x in b))
    for text, herkunft in hinweise.items():
        if rp.MATERIAL_VERWEIS_V10.search(text):
            print(f"  V10-Muster meldet {herkunft}: {text[:110]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--vergleich", nargs="*", default=["evaluationsdaten/vergleich_rag_RAGVGL-FISCHER.csv",
                                                       "evaluationsdaten/vergleich_rag_RAGVGL-V9D.csv"])
    ap.add_argument("--ideen", nargs="*", default=["evaluationsdaten/ideen_test_V8D-IDEEN.csv",
                                                   "evaluationsdaten/ideen_test_V9D-IDEEN.csv"])
    a = ap.parse_args()
    konstruierte_faelle()
    ablauf_mit_simuliertem_modell()
    echte_texte(a.vergleich, a.ideen)
    print(f"\n{'ALLE TESTS BESTANDEN' if not FEHLER else f'{len(FEHLER)} FEHLER'}")
    _sys.exit(1 if FEHLER else 0)

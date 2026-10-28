"""Offline-Test V18: A Schreibweise der Bestätigung, B Formelbeleg, D Zahlen in RECHNUNG belegt, E ERGEBNIS-Name,
K Hochzahl einer Einheit mit ^. Aufruf: python teste_v18_offline.py aus|A|B|ADE|ADEK|ABDE"""
import os, sys, importlib
import pathlib as _pl
sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent"))
mode = sys.argv[1]  # "aus" | "A" | "B" | "AB"
os.environ["LERNASSISTENT_V18"] = "" if mode == "aus" else mode
import pfadsetup  # noqa
import rechenbaustein as rb
ok = fail = 0
def check(n, c):
    global ok, fail
    ok += bool(c); fail += (not c); print(("PASS " if c else "FAIL ") + n)
p = rb.baue_prompt_v3("Frage x = 1 2", "Material")
if rb.V18_A:
    check("A: neue Regel 'genau eine Größe je Zeile' im Prompt", "genau eine Größe je Zeile" in p)
    check("A: altes Beispiel mit zwei Größen in einer Zeile entfernt", "U = 230 V / n = 1500/60" not in p)
    check("A: 'n1 = n/10' als verboten benannt", "nicht „n1 = n/10“" in p)
else:
    check("aus: Prompt unverändert (altes Beispiel)", "U = 230 V / n = 1500/60 1/s" in p)
    check("aus: keine neue Regel", "genau eine Größe je Zeile" not in p)
K1 = "Die Formel J = J0 + J1 ((n1)/n)^2 + J2 ((n2)/n)^2 gilt für Getriebe."
if rb.V18_B:
    check("B: sauber gekürzte Quelle (Formel + …) zählt als belegt",
          rb.quelle_im_material("J = J₀ + J₁ ((n₁)/n)² + …", K1) is True)
    check("B: erfundene Zwischenglieder vor … bleiben unbelegt (F61-Fall)",
          rb.quelle_im_material("J = J₀ + J₁ ((n₁)/n)² + Q₄ ⋅ ⋅ ⋅ + Xyz qwe rty uio pas dfg hjk lzx cvb nm + …", K1) is False)
    check("B: kurze Formel F = P2/v im Material gefunden",
          rb.quelle_im_material("F = (P₂)/v", "Die Schubkraft F = P2/v ergibt sich aus der Leistung.") is True)
    check("B: kurze Formel nicht im Material -> False (keine falsche Belegung)",
          rb.quelle_im_material("F = (P₂)/v", "Ohm'sches Gesetz U = R I.") is False)
    check("B: Quelle ohne Gleichung bleibt False", rb.quelle_im_material("Grundwissen", K1) is False)
    check("B: Quelle mit ||| nur erster Teil zählt",
          rb.quelle_im_material("J = J₀ + J₁ ((n₁)/n)² ||| FORMEL: X = Y", K1) is True)
else:
    check("aus: lange Kürzung mit … wird nicht getrimmt (unverändert False)",
          rb.quelle_im_material("J = J₀ + J₁ ((n₁)/n)² + Q₄ ⋅ ⋅ ⋅ + Xyz qwe rty uio pas dfg hjk lzx cvb nm + …", K1) is False)
    check("aus: kurze Formel bleibt False (unverändert)",
          rb.quelle_im_material("F = (P₂)/v", "Die Schubkraft F = P2/v ergibt sich aus der Leistung.") is False)

# ---- V18-D/E (echte Rohtexte aus dem V18-Kurzlauf und V16) ----
import json as _json
D = _json.load(open(_pl.Path(__file__).with_name("daten_v18.json"), encoding="utf-8"))
ok2 = fail2 = 0
def check2(n, c):
    global ok2, fail2
    ok2 += bool(c); fail2 += (not c); print(("PASS " if c else "FAIL ") + n)
rb.RB_V8 = True
def lauf(roh, frage):
    return rb.rechne_v7(rb.parse_v7(roh), frage, "")
r = lauf(D["R17_v2_bestaetigung"], D["frage_R17"])
if rb.V18_D:
    check2("D: R17 Bestätigung mit selbst gerechneter Zahl 11869.7 -> zwischenwert", r.get("grund") == "zwischenwert")
else:
    check2("aus: R17 Bestätigung ergibt wie bisher 3391 N", r.get("ergebnisse") and abs(r["ergebnisse"][0][1] - 3391) < 2)
r = lauf(D["R17_v2_erste"], D["frage_R17"])
check2("R17 erste Nachrechnung bleibt 1346 N", r.get("ergebnisse") and abs(r["ergebnisse"][0][1] - 1346.05) < 1)
r = lauf(D["F15_wiederholung"], D["frage_F15"])
check2("F15: Wiederholung 'n = 19.298 s^-1' stört nicht, Ergebnis 18,95", r.get("ergebnisse") and abs(r["ergebnisse"][0][1] - 18.947) < 0.01)
r = lauf(D["R20_v2_erste"], D["frage_R20"])
check2("R20 erste Nachrechnung ('M_stR / M_st = …') bleibt 1,266", r.get("ergebnisse") and abs(r["ergebnisse"][0][1] - 1.2664) < 0.001)
r = lauf(D["R20_v2_bestaetigung"], D["frage_R20"])
if rb.V18_E:
    check2("E: R20 Bestätigung, ERGEBNIS-Name nicht berechnet -> ergebnis_name", r.get("grund") == "ergebnis_name")
else:
    check2("aus: R20 Bestätigung fällt wie bisher auf s_K2 = 0,26 zurück", r.get("ergebnisse") and abs(r["ergebnisse"][0][1] - 0.26) < 1e-6)
if rb.V18_D or rb.V18_E:
    p = rb.baue_prompt_v3("x", "y", ("zwischenwert", "F = 1 / 2"))
    check2("Retry-Bericht für zwischenwert vorhanden", "selbst ausgerechnete Zahl" in p and "zwischenwert" in rb.RETRY_GRUENDE)
rb.RB_V8 = False
# ---- V18-K: Hochzahl einer Einheit mit „^“ (RV-v1 R09 Denkmodus) ----
import rechenpruefung as rpr
rpr._V18_K = "K" in (sys.argv[1] if len(sys.argv) > 1 else "")
r09 = [b.get("text", "") for b in rpr.pruefe(D["R09_denk"], "", "RP-v11")]
if rpr._V18_K:
    check2("K: R09 Denkmodus ohne Fehlbefund '150 ^ 2 = 0,015 ^ 2'", not any("150 ^ 2" in t for t in r09))
    check2("K: 'A = 150 cm^2 = 0,015 m^2' ohne Befund", not rpr.pruefe("A = 150 cm^2 = 0,015 m^2", "", "RP-v11"))
    check2("K: 'n = 19,3 s^-1 = 1158 min^-1' ohne Befund", not rpr.pruefe("n = 19,3 s^-1 = 1158 min^-1", "", "RP-v11"))
else:
    check2("aus: R09 Denkmodus mit Fehlbefund wie bisher", any("150 ^ 2" in t for t in r09))
check2("echter Rechenfehler 'x = 2^2 = 5' wird erkannt", any("ergibt 4" in b.get("text", "") for b in rpr.pruefe("x = 2^2 = 5", "", "RP-v11")))
rpr._V18_K = False
print(f"\n{ok + ok2} bestanden, {fail + fail2} fehlgeschlagen")
sys.exit(1 if fail + fail2 else 0)

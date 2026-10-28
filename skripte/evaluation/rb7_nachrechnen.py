"""V15: Rohtexte der Nachrechnung aus einem Lauf (Spalte rb_roh) offline mit RB-v6 und RB-v7 auswerten, ohne Ollama.
Start (aus ~/RAG):  python skripte/evaluation/rb7_nachrechnen.py evaluationsdaten/rechen_varianten_V135.csv [daten/testfragen/rechen_varianten_v1.csv]"""
import sys as _sys, pathlib as _pl, csv
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import rechenbaustein as rb
csv.field_size_limit(10**9)
lauf = _sys.argv[1]
fragen_csv = _sys.argv[2] if len(_sys.argv) > 2 else "daten/testfragen/rechen_varianten_v1.csv"
F = {r["nr"]: r for r in csv.DictReader(open(fragen_csv, encoding="utf-8"))}


def text(res):
    return "; ".join(f"{n} = {rb.rp._zahl_de(w)}" for n, w in res.get("ergebnisse", [])) or res.get("grund", "")


def treffer(res, nr):
    """Vergleich in Grundeinheiten: Ergebnis mit der Einheit unter EINHEIT, Erwartung mit der Einheit der Testfrage."""
    if F[nr]["erwartet"].startswith("T:"):
        return False  # Textantwort, nicht nachrechenbar
    eh = [e.strip() for e in F[nr]["einheit"].split(";")]
    ziele_si = []
    for i, teil in enumerate(F[nr]["erwartet"].replace(",", ".").split(";")):  # ";" = mehrere Werte, "|" = Alternativen
        f = rb.einheit_faktor_v7(eh[i] if i < len(eh) else eh[-1]) or 1
        ziele_si += [float(z) * f for z in teil.split("|") if z.strip()]
    einheiten = rb._einheiten_liste(res) if res.get("ergebnisse") else []
    werte_si = [abs(w) * ((rb.einheit_faktor_v7(e) or 1) if e else 1) for (_, w), e in zip(res.get("ergebnisse", []), einheiten)]
    return any(abs(w - z) <= 0.01 * abs(z) for w in werte_si for z in ziele_si)


n = t6 = t7 = 0
for r in csv.DictReader(open(lauf, encoding="utf-8")):
    if r["nr"] not in F:
        continue
    for roh in [x for x in (r.get("rb_roh") or "").split(" ||| ") if x.strip()]:
        n += 1
        a = rb.rechne_v6(rb.parse_v6(roh), F[r["nr"]]["frage"], "")
        b = rb.rechne_v7(rb.parse_v7(roh), F[r["nr"]]["frage"], "")
        t6 += treffer(a, r["nr"]); t7 += treffer(b, r["nr"])
        if text(a) != text(b):
            print(f"{r['nr']}: RB-v6 {text(a)} -> RB-v7 {text(b)} | erwartet {F[r['nr']]['erwartet']} {F[r['nr']]['einheit']}")
print(f"\n{n} Rohtexte | erwartetes Ergebnis getroffen (in Grundeinheiten verglichen): RB-v6 {t6}, RB-v7 {t7}")

"""OR-v1 (28 Oct 2026): Rechenfragen OHNE RAG. Dasselbe Modell (qwen3.5:9b, temperature 0, seed 42, gleicher Kontext) beantwortet
die Frage ohne Lernmaterial, ohne Formelsuche, ohne Rechenprüfung. Bewertung wie teste_rechen_varianten.py (treffer_v3: erwartete
Zahl in den ersten 600 Zeichen); zusätzlich Spalte erster_satz (streng: erwartete Zahl im ersten Satz).
Prompt (allgemein, ohne Beispiele): Antwort zuerst mit Einheit, dann kurz der Rechenweg.
Start (aus ~/RAG):  python skripte/evaluation/lauf_ohne_rag.py RV1-OHNERAG --fragen daten/testfragen/rechen_varianten_v1.csv"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
import argparse, csv, os, re, time
import rag_pipeline as rp
import rechenpruefung
from teste_rechen_varianten import treffer_v3, zahlen

FELDER = ["nr", "vorlage", "richtig", "erster_satz", "erwartet", "gefunden", "sekunden", "loesung", "fehler"]


def prompt_ohne_rag(frage):
    return ("Du bist ein Lernassistent für Auszubildende in der technischen Berufsausbildung. Beantworte die Frage.\n"
            "Nenne im ersten Satz das Ergebnis mit Einheit. Danach kurz: Formel, eingesetzte Werte und Rechenweg.\n\n"
            f"Frage: {frage}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--fragen", required=True)
    ap.add_argument("--nur", default="")
    a = ap.parse_args()
    fragen = list(csv.DictReader(open(a.fragen, encoding="utf-8")))
    if a.nur:
        fragen = [f for f in fragen if f["nr"] in a.nur.split(",")]
    aus = f"evaluationsdaten/ohne_rag_{a.label}.csv"
    print(f"OHNE RAG | Modell {rp.MODEL_NAME} | CTX={rp.KONTEXT_TOKENS or '-'} | {len(fragen)} Fragen -> {aus}", flush=True)
    fertig = set()
    if os.path.exists(aus):
        fertig = {r["nr"] for r in csv.DictReader(open(aus, encoding="utf-8"))}
    neu = not os.path.exists(aus)
    richtig = streng = 0
    with open(aus, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FELDER)
        if neu:
            w.writeheader()
        for f in fragen:
            if f["nr"] in fertig:
                continue
            t0 = time.perf_counter()
            zeile = {"nr": f["nr"], "vorlage": f.get("vorlage", ""), "erwartet": f["erwartet"] + " " + f["einheit"]}
            try:
                loesung = rp.frage_llm(prompt_ohne_rag(f["frage"]), options=rp.GENERIERUNGS_OPTIONEN)
                eh = [x.strip() for x in f["einheit"].split(";")]
                ok, einzeln = treffer_v3(loesung, f["erwartet"], eh)
                m = rechenpruefung._erster_satz_ende(loesung)
                kopf = loesung[:m.start()] if m else loesung
                ok1, _ = treffer_v3(kopf, f["erwartet"], eh)
                zeile.update({"richtig": "ja" if ok else ("teilweise" if any(einzeln) else "nein"),
                              "erster_satz": "ja" if ok1 else "nein",
                              "gefunden": " ".join(f"{z:g}" for z in zahlen(loesung[:200])[:6]), "loesung": loesung})
                richtig += ok
                streng += ok1
            except Exception as ex:  # ein Fehler stoppt den Lauf nicht
                zeile.update({"richtig": "fehler", "fehler": f"{type(ex).__name__}: {ex}"[:300]})
            zeile["sekunden"] = round(time.perf_counter() - t0, 1)
            w.writerow(zeile); fh.flush()
            print(f"{f['nr']} {zeile['richtig']:9s} erster Satz {zeile.get('erster_satz', '-'):4s} {zeile['sekunden']:6.0f} s | erwartet "
                  f"{zeile['erwartet']} | gefunden {zeile.get('gefunden', '')}", flush=True)
    print(f"\nRichtig (600 Zeichen): {richtig}, davon im ersten Satz: {streng} von {len(fragen) - len(fertig)}. Datei: {aus}", flush=True)


if __name__ == "__main__":
    main()

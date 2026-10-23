"""A/B-Lauf V11b (Formelsuche aus) gegen V12.1 (FS-v2, Standard; mit --fs FS-v1 die alte Variante), beide mit RP-v5, RAG, hybrid_kg_rr. Unbeaufsichtigt, Ergebnis nach jeder Frage gespeichert.
Fragen: N100-Rechenfragen (typ rechnung) + 3 Varianten mit bekannter Lösung (automatisch geprüft).
Start (aus ~/RAG, Ollama läuft):
  python skripte/evaluation/vergleiche_v11b_v12.py V12-AB | tee evaluationsdaten/V12-AB.log
Ausgabe: evaluationsdaten/v12_ab_<SITZUNG>.csv"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import argparse, csv, re, time
from pathlib import Path
from collections import Counter
import rag_pipeline as rp
import formelsuche as fs
from vergleich_mit_ohne_rag import lade_fragen

VARIANTEN = [  # (nr, frage, regex der richtigen Zahl(en))
    ("V-1.32", "Ein Magnetkran hebt einen Stahlträger mit 2,5 m Länge, Querschnitt 0,02 m² und Dichte 7850 kg/m³. "
     "Welche Flussdichte B muss der Hubmagnet mit der Polfläche A = 0,1 m² mindestens haben?", [r"0[,.]3[01]"]),
    ("V-Trafo", "Von einem Drehstrom-Öltransformator 40 kVA, 5000 V / 400 V, Schaltung Yy0 sollen die Bemessungsströme berechnet werden. "
     "Wie groß sind der primäre und der sekundäre Bemessungsstrom?", [r"4[,.]6\d?", r"57[,.][67]"]),
    ("V-1.36", "Ein Transformator hat U1N/U2N = 400 V/100 V und uk = 8 %. Wie groß ist die Sekundärspannung U2 bei rein ohmscher Last, "
     "wenn der ohmsche Spannungsfall vernachlässigt wird?", []),
]
FELDER = ["nr", "typ", "frage", "referenz", "kb_hash", "formel_im_kontext_aus", "formel_im_kontext_an", "ergaenzt_ids", "phrasen",
          "status_aus", "antwort_aus", "pruefung_aus", "befund_aus", "sek_aus",
          "status_an", "antwort_an", "pruefung_an", "befund_an", "sek_an", "gleich", "auto_richtig_aus", "auto_richtig_an", "hand_aus", "hand_an", "anmerkung"]


def lauf(frage, chunks, version):
    rp.RECHEN_PRUEFUNG_VERSION = "RP-v5"
    fs.FORMELSUCHE_VERSION = version
    t0 = time.time()
    erg = rp.beantworte_frage(frage, chunks, methode="hybrid_kg_rr")
    return erg, round(time.time() - t0, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sitzung")
    ap.add_argument("--kb", default="daten/wissensbasen/knowledge_base_fischer_boege_v7r.json")
    ap.add_argument("--fragen", default="daten/testfragen/testfragen_fischer_v2_chunks_beide.csv")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--fs", default="FS-v2", help="Variante gegen V11b: FS-v2 (Standard) oder FS-v1")
    a = ap.parse_args()
    fragen = [{**q, "erwartet": []} for q in lade_fragen(a.fragen, "") if q["typ"] == "rechnung"][: a.limit]
    fragen += [{"nr": n, "typ": "variante", "frage": f, "referenz": "", "erwartet": e} for n, f, e in VARIANTEN]
    chunks = rp.lade_wissensbasis(a.kb)
    kb_hash = rp.berechne_kb_hash(a.kb)
    out = Path("evaluationsdaten") / f"v12_ab_{a.sitzung}.csv"
    print(f"{len(fragen)} Fragen | KB {a.kb} ({kb_hash}) | {rp.SCAFFOLDING_VERSION}\n", flush=True)
    # Arme getrennt nacheinander (nicht je Frage abwechselnd): Ollama liefert für dieselbe Anfrage beim ersten Mal ("kalt")
    # eine andere Antwort als bei Wiederholung ("warm", teste_determinismus.py 23 Oct 2026). Im Wechsel wäre der zweite Arm
    # immer warm und damit nicht vergleichbar.
    zeilen = [{"nr": q["nr"], "typ": q["typ"], "frage": q["frage"], "referenz": q["referenz"], "kb_hash": kb_hash} for q in fragen]

    def speichere():
        with open(out, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FELDER); w.writeheader()
            for r in zeilen: w.writerow({k: r.get(k, "") for k in FELDER})
    for tag, ver in (("aus", "aus"), ("an", a.fs)):
        print(f"\n--- Arm '{tag}' (Formelsuche {ver}) ---", flush=True)
        for q, z in zip(fragen, zeilen):
            try:
                erg, sek = lauf(q["frage"], chunks, ver)
            except Exception as e:
                erg, sek = {"status": "FEHLER", "loesung": str(e)[:200]}, 0
            z[f"sek_{tag}"] = sek
            z[f"status_{tag}"] = erg.get("status", "")
            z[f"antwort_{tag}"] = erg.get("loesung", "")
            z[f"pruefung_{tag}"] = erg.get("rechen_pruefung", "")
            z[f"befund_{tag}"] = erg.get("rechen_befund", "")
            tc = erg.get("top_chunks", [])
            z[f"formel_im_kontext_{tag}"] = any(fs.hat_formel(c.get("text", "")) for c in tc)
            if tag == "an":
                info = erg.get("formelsuche") or {}
                z["ergaenzt_ids"] = ";".join(info.get("ids", [])) if info.get("angenommen", a.fs == "FS-v1") else ""
                z["phrasen"] = ";".join(info.get("phrasen", []))
            if q["erwartet"]:
                z[f"auto_richtig_{tag}"] = all(re.search(r, erg.get("loesung", "").split("Begründung")[0]) for r in q["erwartet"])
            print(f"[{q['nr']:>7}] {tag}: prüf {z[f'pruefung_{tag}'] or '-':<14} sek {sek:<6} auto: {z.get(f'auto_richtig_{tag}', '')}", flush=True)
            speichere()
    for z in zeilen:
        z["gleich"] = z.get("antwort_aus", "").strip() == z.get("antwort_an", "").strip()
        z.setdefault("ergaenzt_ids", "")
    speichere()
    print("\n=== Zusammenfassung ===")
    print("Formel im Kontext aus/an:", sum(z["formel_im_kontext_aus"] for z in zeilen), "/", sum(z["formel_im_kontext_an"] for z in zeilen), "von", len(zeilen))
    print("FS hat ergänzt:", sum(bool(z["ergaenzt_ids"]) for z in zeilen), "| Antwort geändert:", sum(not z["gleich"] for z in zeilen))
    for t in ("aus", "an"):
        v = [z for z in zeilen if z.get(f"auto_richtig_{t}") != ""  and f"auto_richtig_{t}" in z]
        print(f"Varianten automatisch richtig ({t}):", sum(bool(z[f'auto_richtig_{t}']) for z in v), "/", len(v))
    print("Mittlere Sekunden aus/an:", round(sum(z["sek_aus"] for z in zeilen) / len(zeilen), 1), "/", round(sum(z["sek_an"] for z in zeilen) / len(zeilen), 1))
    print("Gespeichert:", out)


if __name__ == "__main__":
    main()

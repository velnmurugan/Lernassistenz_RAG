#!/usr/bin/env python3
"""Bild-Transkriptionstest T-v1 (23 Oct 2026): liest Aufgaben-Screenshots mit zwei Vision-Modellen
und schreibt Text + Abbildungsbeschreibung. Nur Messung, ändert nichts an der App.

Aufruf (aus ~/RAG):
  python skripte/evaluation/teste_bild_transkription.py [ordner] [--modelle qwen3.5:9b qwen2.5vl:7b]
Standard-Ordner: testbilder/   Ausgabe: evaluationsdaten/bildtest_<zeit>.csv (+ .md zum Lesen)
"""
import argparse, base64, csv, datetime, sys, time
from pathlib import Path

import requests

sys.path.insert(0, "lernassistent")
try:
    from rag_pipeline import OLLAMA_URL
except Exception as e:  # Notlösung: Host manuell angeben
    OLLAMA_URL = None
    print("WARNUNG: OLLAMA_URL nicht aus rag_pipeline lesbar:", e)

PROMPT = """Du siehst die Aufnahme einer Aufgabe aus einem technischen Lehrbuch.
1. AUFGABENTEXT: Schreibe den Text der Aufgabe wörtlich ab. Formeln im Klartext, Zahlen und Einheiten genau wie im Bild.
2. ABBILDUNG: Beschreibe die Abbildung, falls vorhanden. Erster Satz: Art (Schaltplan, Diagramm mit Achsen, Schnittbild, Foto ...). Danach Bauteile mit ihren Werten und Beschriftungen, bei Diagrammen die Achsengrößen und den Kurvenverlauf. Wie die Bauteile verbunden sind (Reihe, parallel), nur wenn eindeutig erkennbar.
Gib nur wieder, was eindeutig zu sehen ist. Ergänze nichts. Was unleserlich ist, schreibe als [unleserlich].
Antworte auf Deutsch, ohne Markdown und ohne LaTeX, in genau diesem Format:
AUFGABENTEXT: ...
ABBILDUNG: ... (oder: keine Abbildung)"""

OPT = {"temperature": 0, "seed": 42, "num_predict": 700, "repeat_penalty": 1.1}


def transkribiere(url, modell, bild: Path):
    b64 = base64.b64encode(bild.read_bytes()).decode()
    payload = {"model": modell, "prompt": PROMPT, "images": [b64], "stream": False, "think": False, "options": OPT}
    t0 = time.time()
    try:
        r = requests.post(url, json=payload, timeout=300)
        r.raise_for_status()
        return r.json()["response"].strip(), round(time.time() - t0, 1), ""
    except Exception as e:
        return "", round(time.time() - t0, 1), str(e)[:200]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ordner", nargs="?", default="testbilder")
    ap.add_argument("--modelle", nargs="+", default=["qwen3.5:9b", "qwen2.5vl:7b"])
    ap.add_argument("--url", default=None)
    a = ap.parse_args()
    url = a.url or OLLAMA_URL
    if not url:
        sys.exit("Keine Ollama-URL: --url http://<host>:11434/api/generate angeben")
    bilder = sorted(p for p in Path(a.ordner).iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
    if not bilder:
        sys.exit(f"Keine Bilder in {a.ordner}")
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path("evaluationsdaten"); out.mkdir(exist_ok=True)
    csvp, mdp = out / f"bildtest_{stamp}.csv", out / f"bildtest_{stamp}.md"
    print(f"{len(bilder)} Bilder, Modelle {a.modelle}, URL {url}")
    with open(csvp, "w", encoding="utf-8", newline="") as fc:
        w = csv.writer(fc)
        w.writerow(["bild", "modell", "sekunden", "fehler", "transkription"])
        # je Modell alle Bilder (ein Modellwechsel statt vieler)
        ergebnisse = {}
        for m in a.modelle:
            print(f"== {m}")
            for i, b in enumerate(bilder, 1):
                text, sek, fehler = transkribiere(url, m, b)
                ergebnisse[(b.name, m)] = (text, sek, fehler)
                w.writerow([b.name, m, sek, fehler, text]); fc.flush()
                print(f"  [{i}/{len(bilder)}] {b.name}: {sek} s {'FEHLER ' + fehler if fehler else ''}")
    with open(mdp, "w", encoding="utf-8") as fm:
        for b in bilder:
            fm.write(f"\n## {b.name}\n")
            for m in a.modelle:
                text, sek, fehler = ergebnisse[(b.name, m)]
                fm.write(f"\n**{m}** ({sek} s){' FEHLER: ' + fehler if fehler else ''}\n\n{text}\n")
    print("Fertig:", csvp, mdp)


if __name__ == "__main__":
    main()

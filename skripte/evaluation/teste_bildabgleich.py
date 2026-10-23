"""Bildabgleich-Experiment BA-v1 (24 Oct 2026): Findet ein hochgeladenes Bild die passende Abbildung in der Wissensbasis, ohne dass das
Sprachmodell das Bild erkennen muss? Die Wissensbasis hat 'abbildung'-Chunks (Bildunterschrift, Abschnittspfad = Thema, Seite, Bilddatei).
Verfahren: ORB-Merkmale (OpenCV) + Ratio-Test + RANSAC-Homographie; Zahl der Inlier = Treffergüte. Funktioniert auch, wenn die Abbildung
nur ein Ausschnitt eines Screenshots ist. Zusätzlich dHash (nur für gleich zugeschnittene Bilder).
Nur Messung, ändert nichts an der App. Benötigt opencv-python (pip install opencv-python-headless) und die extrahierten Buchbilder.

Start (aus ~/RAG):
  python skripte/evaluation/teste_bildabgleich.py BA-01 [--kb ...] [--bildwurzel daten/extraktion] [--ordner testbilder]
Eingabe: alle Bilder in testbilder/ und testbilder/abbildungen/.
Ausgabe: evaluationsdaten/bildabgleich_<SITZUNG>.csv (+ .md): je Testbild die 5 besten Treffer mit Inliern, Bildunterschrift, Thema, Seite.
Beurteilung: Spalte 'richtig' (ja/nein) für Rang 1 von Hand ausfüllen; Faustregel: ab ca. 15 Inliern meist dieselbe Abbildung."""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import argparse, csv, json, pickle, re, time
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError:
    raise SystemExit("opencv-python fehlt: pip install opencv-python-headless")

ENDUNGEN = (".png", ".jpg", ".jpeg", ".webp")
INLIER_MIN = 15


import bildabgleich as ba
lade = lambda pfad: ba.lade_grau(pfad=pfad)
dhash, merkmale, inlier = ba.dhash, ba.merkmale, ba.inlier


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sitzung")
    ap.add_argument("--kb", default="daten/wissensbasen/knowledge_base_fischer_boege_v7r.json")
    ap.add_argument("--bildwurzel", default="daten/extraktion")
    ap.add_argument("--ordner", default="testbilder")
    ap.add_argument("--top", type=int, default=5)
    a = ap.parse_args()
    t0 = time.time()
    kb = [(c, (m, h)) for c, (m, h) in ba.baue_index(a.kb, a.bildwurzel)]
    print(f"{len(kb)} Abbildungen der Wissensbasis indiziert in {time.time() - t0:.0f} s (Bildwurzel {a.bildwurzel})", flush=True)
    if not kb:
        raise SystemExit("Keine Abbildungs-Chunks mit auffindbarer Bilddatei (Chunk-Typ 'abbildung', Feld 'bild'; --bildwurzel prüfen).")
    orb = cv2.ORB_create(nfeatures=1000)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING)

    ordner = Path(a.ordner)
    tests = sorted(p for p in ordner.iterdir() if p.suffix.lower() in ENDUNGEN) if ordner.exists() else []
    if (ordner / "abbildungen").exists():
        tests += sorted(p for p in (ordner / "abbildungen").iterdir() if p.suffix.lower() in ENDUNGEN)
    out = Path("evaluationsdaten") / f"bildabgleich_{a.sitzung}.csv"
    felder = ["testbild", "rang", "inlier", "dhash_abstand", "chunk_id", "typ_treffer", "seite", "thema", "unterschrift", "sekunden", "plausibel", "richtig"]
    zeilen = []
    md = []
    for p in tests:
        img = lade(p)
        if img is None:
            continue
        t1 = time.time()
        q = merkmale(img, orb)
        qh = dhash(img)
        erg = []
        for c, (m, h) in kb:
            erg.append((inlier(q, m, bf), bin(qh ^ h).count("1"), c))
        erg.sort(key=lambda x: (-x[0], x[1]))
        sek = round(time.time() - t1, 1)
        md.append(f"## {p.name} ({sek} s)\n")
        for rang, (n, d, c) in enumerate(erg[: a.top], 1):
            unterschrift = (c["text"].split("\n")[0])[:140]
            zeilen.append({"testbild": p.name, "rang": rang, "inlier": n, "dhash_abstand": d, "chunk_id": c["id"], "typ_treffer": c.get("typ"),
                           "seite": c.get("seite", ""), "thema": c.get("thema", ""), "unterschrift": unterschrift, "sekunden": sek,
                           "plausibel": n >= INLIER_MIN, "richtig": ""})
            md.append(f"{rang}. Inlier {n}, dHash-Abstand {d} · {c['id']} S. {c.get('seite','')} · {c.get('thema','')} · {unterschrift}")
        md.append("")
        print(f"{p.name}: bester Treffer {erg[0][0]} Inlier – {erg[0][2].get('thema','')[:60]} | {erg[0][2]['text'].splitlines()[0][:60]} ({sek} s)", flush=True)
        with open(out, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=felder); w.writeheader(); w.writerows(zeilen)
        out.with_suffix(".md").write_text("\n".join(md), encoding="utf-8")
    plaus = sum(1 for z in zeilen if z["rang"] == 1 and z["plausibel"])
    print(f"\nFertig: {out} · {plaus}/{len(tests)} Testbilder mit plausiblem Treffer (≥{INLIER_MIN} Inlier)")


if __name__ == "__main__":
    main()

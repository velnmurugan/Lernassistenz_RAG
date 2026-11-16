"""
baue_wissensbasis_struktur.py
-----------------------------
Baut aus einer PDF zwei Wissensbasen mit strukturtreuem Chunking:
  <name>_v7a.json  Text, Tabellen, Abbildungen nur mit Bildunterschrift
  <name>_v7b.json  wie v7a, Abbildungen zusätzlich mit VLM-Bildbeschreibung
So unterscheidet sich v7b von v7a nur durch die Bildbeschreibungen (eine Änderung pro Version).

Schritte (jeder wird übersprungen, wenn sein Ergebnis schon existiert -> fortsetzbar):
  1. MinerU-Extraktion   -> daten/extraktion/<name>/
  2. Bildbeschreibungen  -> daten/extraktion/<name>/bildbeschreibungen_<modell>_B-v1.json
  3. Chunking + Schreiben der beiden Wissensbasen -> daten/wissensbasen/
  4. Prüfdatei (30 zufällige Bildbeschreibungen für die Handprüfung)

Start:
  python skripte/wissensbasis/baue_wissensbasis_struktur.py \
      --pdf daten/quellen/fischer/<datei>.pdf --name fischer --methode ocr
Optionen: --methode ocr (alles per OCR), --ohne-vlm, --vlm-modell qwen2.5vl:7b, --max-bilder 20 (Test)

Neue Version neben der alten bauen (alte Wissensbasen bleiben unverändert, z. B. nach einer Änderung
in pdf_struktur.py; vorhandene Extraktion und Bildbeschreibungen werden wiederverwendet):
  python skripte/wissensbasis/baue_wissensbasis_struktur.py --pdf daten/quellen/fischer/<datei>.pdf \
      --name fischer --kennung v7c --vergleich daten/wissensbasen/knowledge_base_fischer_v7b.json
  -> nur knowledge_base_fischer_v7c.json (mit Bildbeschreibungen) + Liste der geänderten Chunks

⚠ Ausgaben enthalten den Buchtext -> daten/extraktion/ und daten/wissensbasen/ sind in .gitignore.
"""
import sys as _sys, pathlib as _pl  # Projektpfade (lernassistent/pfadsetup.py)
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import argparse
import datetime
import json
from pathlib import Path

import pdf_struktur as ps
import bildbeschreibung as bb


def vergleiche(chunks, pfad_alt):
    """Gibt aus, welche Chunks sich gegenüber einer älteren Wissensbasis geändert haben (Text enthält Buch-
    inhalte -> Ausgabe nur lokal ansehen)."""
    alt = json.loads(Path(pfad_alt).read_text(encoding="utf-8"))
    alt = alt["chunks"] if isinstance(alt, dict) else alt
    print(f"    Vergleich mit {pfad_alt}: alt {len(alt)} Chunks, neu {len(chunks)} Chunks")
    alt_texte = {c["text"] for c in alt}
    neu_texte = {c["text"] for c in chunks}
    nur_neu = [c for c in chunks if c["text"] not in alt_texte]
    print(f"    geänderte oder neue Chunk-Texte: {len(nur_neu)}, weggefallene: {len(alt_texte - neu_texte)}")
    from collections import Counter
    print(f"    nach Typ: {dict(Counter(c.get('typ') for c in nur_neu))}")
    alt_nach_id = {c["id"]: c["text"] for c in alt}
    for c in nur_neu[:15]:
        import difflib
        a, n = alt_nach_id.get(c["id"], "").split(), c["text"].split()
        ops = difflib.SequenceMatcher(None, a, n, autojunk=False).get_opcodes()
        diff = [f"'{' '.join(a[i1:i2])}' -> '{' '.join(n[j1:j2])}'" for t, i1, i2, j1, j2 in ops if t != "equal"][:4]
        print(f"      {c['id']} ({c.get('typ')}, S. {c.get('seite')}): {'; '.join(diff) or '(Grenzen verschoben)'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--name", required=True, help="Kurzname, z. B. fischer")
    ap.add_argument("--methode", default="auto", choices=["auto", "ocr", "txt"])
    ap.add_argument("--ohne-vlm", action="store_true")
    ap.add_argument("--vlm-modell", default=bb.VLM_MODELL)
    ap.add_argument("--max-bilder", type=int, default=None)
    ap.add_argument("--kennung", default=None,
                    help="z. B. v7c: schreibt NUR knowledge_base_<name>_<kennung>.json (mit Bildbeschreibungen)")
    ap.add_argument("--vergleich", default=None, help="ältere Wissensbasis: geänderte Chunks auflisten")
    args = ap.parse_args()

    ausgabe = Path("daten/extraktion") / args.name
    ziel_ordner = Path("daten/wissensbasen")
    ziel_ordner.mkdir(parents=True, exist_ok=True)

    # 1. Extraktion
    try:
        content = ps.finde_content_list(ausgabe, Path(args.pdf).stem)
        print(f"1/4 Extraktion vorhanden: {content}")
    except FileNotFoundError:
        print("1/4 MinerU-Extraktion läuft (dauert) …", flush=True)
        content = ps.mineru_ausfuehren(args.pdf, ausgabe, args.methode)
    eintraege, bildordner = ps.lade_content_list(content)
    print(f"    {len(eintraege)} Elemente in der content_list")

    # 2. Bildbeschreibungen
    beschreibungen = {}
    cache = ausgabe / f"bildbeschreibungen_{args.vlm_modell.replace(':', '-')}_{bb.BILD_PROMPT_VERSION}.json"
    if not args.ohne_vlm:
        print(f"2/4 Bildbeschreibungen mit {args.vlm_modell} …", flush=True)
        beschreibungen = bb.beschreibe_alle(eintraege, bildordner, cache, args.vlm_modell, args.max_bilder)
    else:
        print("2/4 übersprungen (--ohne-vlm)")

    # 3. Chunking
    meta = {"quelle": Path(args.pdf).name, "extraktion": f"MinerU {ps.MINERU_BACKEND}/{args.methode}",
            "chunking": f"struktur, Ziel {ps.ZIEL_WOERTER} Wörter, ohne Überlappung",
            "bildordner": str(bildordner), "erstellt": datetime.datetime.now().isoformat(timespec="seconds")}
    varianten = [(args.kennung, True)] if args.kennung else [("v7a", False), ("v7b", True)]
    for suffix, mit in varianten:
        if mit and not beschreibungen:
            print("3/4 v7b übersprungen (keine Bildbeschreibungen)")
            continue
        chunks = ps.strukturchunks(eintraege, beschreibungen, mit_beschreibungen=mit)
        ziel = ziel_ordner / f"knowledge_base_{args.name}_{suffix}.json"
        m = {**meta, "bildbeschreibungen": f"{args.vlm_modell} {bb.BILD_PROMPT_VERSION}" if mit else "keine"}
        ziel.write_text(json.dumps({"meta": m, "chunks": chunks}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"3/4 {ziel}: {ps.statistik(chunks)}")
        if args.vergleich and mit:
            vergleiche(chunks, args.vergleich)

    # 4. Prüfdatei
    if beschreibungen:
        pruef = ausgabe / "bildbeschreibungen_pruefung.csv"
        bb.schreibe_pruefdatei(cache, pruef)
        print(f"4/4 Prüfdatei für die Handprüfung: {pruef}")


if __name__ == "__main__":
    main()

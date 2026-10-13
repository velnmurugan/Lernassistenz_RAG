"""
ordne_chunks_zu.py
------------------
Trägt in eine Testfragen-CSV die Chunk-IDs ein, indem der kurze Ankertext (Spalte
"anker") in der Wissensbasis gesucht wird. Nötig, weil Chunk-IDs erst beim Bau der
Wissensbasis entstehen.

Vergleich robust gegen PDF-Extraktion: Silbentrennung am Zeilenende zusammengeführt,
Leerraum vereinheitlicht, Kleinschreibung. Kommt der Anker in mehreren Chunks vor
(1-Satz-Überlappung benachbarter Chunks), wird der erste genommen und gemeldet.

Start:
  python skripte/wissensbasis/ordne_chunks_zu.py daten/testfragen/testfragen_fischer_v1.csv \
         daten/wissensbasen/knowledge_base_fischer_v7a.json [Ausgabe.csv]
Ausgabe: <Fragen>_chunks.csv bzw. die angegebene Datei (Original bleibt unverändert)
"""
import sys as _sys, pathlib as _pl  # Projektpfade (lernassistent/pfadsetup.py)
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import csv
import re
import unicodedata
import sys
from pathlib import Path

from rag_pipeline import lade_wissensbasis


def norm(t):
    """Vergleich ohne Leerraum und ohne Bindestriche: Die PDF-Extraktion setzt teils Leerzeichen
    mitten ins Wort ("dar f", "Drehstro m") und Trennstriche sind nicht von echten Bindestrichen
    zu unterscheiden. Kleinschreibung."""
    t = unicodedata.normalize("NFKC", t or "")  # Ligaturen wie "ﬂ" -> "fl"
    return re.sub(r"[\s\-‐‑–]+", "", t).lower()


def main():
    if len(sys.argv) not in (3, 4):
        sys.exit("Aufruf: python ordne_chunks_zu.py <fragen.csv> <wissensbasis.json> [<ausgabe.csv>]")
    fragen_pfad, kb_pfad = Path(sys.argv[1]), sys.argv[2]
    chunks = lade_wissensbasis(kb_pfad)
    texte = [(c["id"], norm(c["text"]), c.get("thema", "")) for c in chunks]
    with open(fragen_pfad, encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        felder, zeilen = r.fieldnames, list(r)

    gefunden = fehlt = 0
    for z in zeilen:
        anker = norm(z.get("anker", ""))
        if not anker:
            continue
        treffer = [(cid, th) for cid, t, th in texte if anker in t]
        if not treffer:  # Ersatz: erste 4 Wörter des Ankers
            kurz = norm(" ".join(z["anker"].split()[:4]))
            treffer = [(cid, th) for cid, t, th in texte if kurz in t]
        if treffer:
            z["chunk_id"] = treffer[0][0]
            z["thema"] = z.get("thema") or treffer[0][1]
            gefunden += 1
            extra = f"  (+{len(treffer) - 1} weitere: {', '.join(c for c, _ in treffer[1:4])})" if len(treffer) > 1 else ""
            print(f"[{z['nr']:>2}] {treffer[0][0]}{extra}")
        else:
            fehlt += 1
            print(f"[{z['nr']:>2}] NICHT GEFUNDEN – Anker prüfen: {z['anker']!r}")

    ziel = Path(sys.argv[3]) if len(sys.argv) == 4 else fragen_pfad.with_name(fragen_pfad.stem + "_chunks.csv")
    with open(ziel, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=felder)
        w.writeheader()
        w.writerows(zeilen)
    print(f"\n{gefunden} zugeordnet, {fehlt} nicht gefunden -> {ziel}")


if __name__ == "__main__":
    main()

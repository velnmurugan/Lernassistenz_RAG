"""
pilot_extraktion.py
-------------------
Kurzer Probelauf VOR dem Nachtlauf (~5–15 min): nimmt einige Seiten einer PDF und zeigt
nebeneinander, was pypdf (bisher), PyMuPDF und MinerU (auto / ocr) daraus machen, dazu die
entstehenden Struktur-Chunks und VLM-Beschreibungen einiger Abbildungen.
Ergebnis: protokolle/pilot_<name>.html (im Browser öffnen). Enthält Buchtext -> nicht teilen.

Start (Fischer, Seiten mit Formeln, Tabellen, Abbildungen):
  python skripte/wissensbasis/pilot_extraktion.py --pdf daten/quellen/fischer/978-3-658-25644-9.pdf \
      --name fischer --seiten 147,157,180,212,339,405
"""
import sys as _sys, pathlib as _pl  # Projektpfade (lernassistent/pfadsetup.py)
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import argparse
import base64
import html
from pathlib import Path

import pymupdf

import pdf_struktur as ps
import bildbeschreibung as bb


def b64_png(pix):
    return base64.b64encode(pix.tobytes("png")).decode()


def mineru_seitentexte(eintraege):
    seiten = {}
    for e in eintraege:
        p = int(e.get("page_idx", 0))
        typ = e.get("type")
        if typ == "table":
            t = "[TABELLE] " + ps._liste(e.get("table_caption")) + "\n" + ps.tabelle_als_text(e.get("table_body", ""))
        elif typ == "image":
            t = "[ABBILDUNG] " + ps._liste(e.get("image_caption") or e.get("img_caption"))
        elif typ == "equation":
            t = "[FORMEL] " + (e.get("text") or "")
        else:
            t = ("# " if e.get("text_level") else "") + (e.get("text") or "")
        seiten.setdefault(p, []).append(t)
    return {p: "\n\n".join(v) for p, v in seiten.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--seiten", required=True, help="PDF-Seiten (1-basiert), kommagetrennt")
    ap.add_argument("--vlm-modell", default=bb.VLM_MODELL)
    ap.add_argument("--max-bilder", type=int, default=6)
    args = ap.parse_args()
    seiten = [int(s) for s in args.seiten.split(",")]

    basis = Path("daten/extraktion") / f"pilot_{args.name}"
    basis.mkdir(parents=True, exist_ok=True)
    quelle = pymupdf.open(args.pdf)
    klein = pymupdf.open()
    for s in seiten:
        klein.insert_pdf(quelle, from_page=s - 1, to_page=s - 1)
    klein_pfad = basis / "pilot.pdf"
    klein.save(klein_pfad)

    # Bisheriges Verfahren (pypdf) und PyMuPDF
    from pypdf import PdfReader
    pypdf_texte = [p.extract_text() or "" for p in PdfReader(str(klein_pfad)).pages]
    mupdf_texte = [p.get_text() for p in klein]
    bilder_seiten = [b64_png(p.get_pixmap(dpi=60)) for p in klein]

    # MinerU auto und ocr
    ergebnisse = {}
    for methode in ("auto", "ocr"):
        try:
            content = ps.finde_content_list(basis / methode, "pilot")
        except FileNotFoundError:
            try:
                content = ps.mineru_ausfuehren(klein_pfad, basis / methode, methode)
            except Exception as ex:
                print(f"MinerU {methode} FEHLER: {ex}")
                continue
        ergebnisse[methode] = ps.lade_content_list(content)

    # Chunks + VLM (auf Basis von MinerU auto)
    chunk_html, vlm_html = "", ""
    if "auto" in ergebnisse:
        eintraege, bildordner = ergebnisse["auto"]
        try:
            beschreibungen = bb.beschreibe_alle(eintraege, bildordner, basis / "bildbeschreibungen_pilot.json",
                                                args.vlm_modell, args.max_bilder)
        except Exception as ex:
            print(f"VLM FEHLER: {ex}")
            beschreibungen = {}
        chunks = ps.strukturchunks(eintraege, beschreibungen, mit_beschreibungen=True)
        chunk_html = f"<p>{html.escape(ps.statistik(chunks))}</p>" + "".join(
            f"<div class=chunk><b>{c['id']}</b> · S. {c['seite']} · {c['typ']} · <i>{html.escape(c['thema'])}</i>"
            f"<pre>{html.escape(c['text'])}</pre></div>" for c in chunks)
        for rel, text in beschreibungen.items():
            if not text:
                continue
            img = Path(bildordner) / rel
            b64 = base64.b64encode(img.read_bytes()).decode() if img.exists() else ""
            vlm_html += (f"<div class=vlm><img src='data:image/jpeg;base64,{b64}'>"
                         f"<pre>{html.escape(text)}</pre></div>")

    zeilen = []
    for i, s in enumerate(seiten):
        spalten = [("pypdf (bisher)", pypdf_texte[i]), ("PyMuPDF", mupdf_texte[i])]
        for methode, (eintraege, _) in ergebnisse.items():
            spalten.append((f"MinerU {methode}", mineru_seitentexte(eintraege).get(i, "")))
        zellen = "".join(f"<td><h4>{n}</h4><pre>{html.escape(t)}</pre></td>" for n, t in spalten)
        zeilen.append(f"<tr><td><h4>Seite {s}</h4><img src='data:image/png;base64,{bilder_seiten[i]}'></td>{zellen}</tr>")

    seite = f"""<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Pilot Extraktion {args.name}</title>
<style>body{{font:13px system-ui;margin:16px}}table{{border-collapse:collapse}}td{{vertical-align:top;border:1px solid #ddd;padding:6px;max-width:420px}}
pre{{white-space:pre-wrap;font-size:12px}}img{{max-width:380px}}.chunk,.vlm{{border:1px solid #ddd;border-radius:6px;padding:8px;margin:8px 0}}
.vlm{{display:flex;gap:12px}}.vlm img{{max-width:320px}}</style></head><body>
<h1>Pilot: Extraktion {html.escape(args.name)}</h1><p>Seiten {args.seiten}. Prüfen: Formeln (=, √, ·), Tabellen, Lesereihenfolge, Wortabstände.</p>
<h2>1. Vergleich je Seite</h2><table>{''.join(zeilen)}</table>
<h2>2. Struktur-Chunks (MinerU auto, mit Bildbeschreibungen)</h2>{chunk_html or '<p>nicht verfügbar</p>'}
<h2>3. Bildbeschreibungen ({html.escape(args.vlm_modell)})</h2>{vlm_html or '<p>nicht verfügbar</p>'}
</body></html>"""
    Path("protokolle").mkdir(exist_ok=True)
    ziel = Path("protokolle") / f"pilot_{args.name}.html"
    ziel.write_text(seite, encoding="utf-8")
    print(f"Pilotseite: {ziel}")


if __name__ == "__main__":
    main()

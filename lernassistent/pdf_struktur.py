"""
pdf_struktur.py
---------------
V7: Strukturtreue Extraktion und Chunking (claude/Entwicklung_und_Evaluation.md, V7).

1. Extraktion mit MinerU (Layout-Erkennung, Formeln als LaTeX, Tabellen strukturiert,
   Abbildungen als Bildausschnitte, Überschriften). Quelle: MinerU, eingesetzt bei
   Yu et al. (2026, SF-RAG). MinerU läuft in einer EIGENEN conda-Umgebung ("mineru"),
   damit seine Abhängigkeiten (torch, transformers) die Projektumgebung nicht verändern.
2. Chunking entlang der Dokumentstruktur statt fester Satzzahl:
   - Grenzen an Überschriften und Absätzen; jeder Chunk kennt seinen Abschnittspfad
     (SF-RAG: Yu et al., 2026).
   - Zielgröße ca. 150–300 Tokens, keine Überlappung (Bennani & Moslonka, 2026).
   - Tabellen als eigene Chunks mit Überschrift (T²-RAGBench: Strich et al., 2026).
   - Formeln bleiben als LaTeX im Text.
   - Abbildungen: eigener Chunk aus Bildunterschrift (V7a) plus optional einer
     automatischen Bildbeschreibung durch ein kleines VLM (V7b, bildbeschreibung.py;
     Saucă & Rusnac, 2026).
Alle Regeln sind dokumentunabhängig (keine Sonderfälle für ein bestimmtes Buch).
"""
import html
import json
import os
import re
import shlex
import subprocess
import unicodedata
from pathlib import Path

# Befehl für MinerU; über die Umgebungsvariable MINERU_BEFEHL änderbar.
MINERU_BEFEHL = shlex.split(os.environ.get("MINERU_BEFEHL", "conda run --no-capture-output -n mineru mineru"))
MINERU_BACKEND = "pipeline"   # Layout-Modell + OCR + Formel-/Tabellenerkennung
MINERU_SPRACHE = "latin"      # OCR-Sprachmodell für lateinische Schrift (Deutsch)

ZIEL_WOERTER = 200            # ~ 260 Tokens; Obergrenze pro Text-Chunk
MIN_WOERTER = 40              # kleinere Reste werden mit dem nächsten Absatz desselben Abschnitts verbunden
TABELLE_MAX_WOERTER = 300

_NUMMERIERT = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+\S")


# ---------------------------------------------------------------------------
# 1. Extraktion
# ---------------------------------------------------------------------------
def mineru_ausfuehren(pdf, ausgabe, methode="auto"):
    """Ruft MinerU auf. methode: auto (Textebene + Erkennung) | ocr (alles per OCR).
    Ergebnis: Ordner mit *_content_list.json, *.md und images/."""
    ausgabe = Path(ausgabe)
    ausgabe.mkdir(parents=True, exist_ok=True)
    befehl = MINERU_BEFEHL + ["-p", str(pdf), "-o", str(ausgabe), "-b", MINERU_BACKEND,
                              "-m", methode, "-l", MINERU_SPRACHE]
    print("MinerU:", " ".join(befehl), flush=True)
    subprocess.run(befehl, check=True)
    return finde_content_list(ausgabe, Path(pdf).stem)


def finde_content_list(ausgabe, stamm=None):
    kandidaten = sorted(Path(ausgabe).rglob("*_content_list.json"))
    if stamm:
        passend = [k for k in kandidaten if k.name.startswith(stamm)]
        kandidaten = passend or kandidaten
    if not kandidaten:
        raise FileNotFoundError(f"Keine *_content_list.json unter {ausgabe}")
    return kandidaten[0]


def lade_content_list(pfad):
    pfad = Path(pfad)
    with open(pfad, encoding="utf-8") as f:
        eintraege = json.load(f)
    return eintraege, pfad.parent  # Bildpfade sind relativ zu diesem Ordner


# ---------------------------------------------------------------------------
# 2. Bereinigung (allgemein, dokumentunabhängig)
# ---------------------------------------------------------------------------
def bereinige(text):
    text = unicodedata.normalize("NFKC", text or "")
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip()


def tabelle_als_text(html_text):
    t = html_text or ""
    t = re.sub(r"(?i)</t[dh]\s*>", " | ", t)
    t = re.sub(r"(?i)</tr\s*>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t)
    zeilen = [re.sub(r"\s+", " ", z).strip(" |") for z in t.splitlines()]
    return "\n".join(z for z in zeilen if z)


def _liste(wert):
    if isinstance(wert, list):
        return " ".join(bereinige(str(w)) for w in wert if w)
    return bereinige(str(wert)) if wert else ""


def _woerter(t):
    return len(t.split())


def _saetze(text):
    try:
        from rag_pipeline import _satzsplit
        return _satzsplit(text)
    except Exception:
        return re.split(r"(?<=[.!?])\s+", text)


# ---------------------------------------------------------------------------
# 3. Chunking
# ---------------------------------------------------------------------------
def strukturchunks(eintraege, bildbeschreibungen=None, mit_beschreibungen=False):
    """content_list (MinerU) -> Chunks im Format der Wissensbasis.
    bildbeschreibungen: {img_path: beschreibung}; nur genutzt, wenn mit_beschreibungen=True.
    Chunk-Felder: id, thema (Abschnittspfad), text, seite (1-basiert), typ (text|tabelle|abbildung),
    bild (relativer Bildpfad bei abbildung/tabelle)."""
    bildbeschreibungen = bildbeschreibungen or {}
    chunks, puffer = [], []
    pfad = []                # [(ebene, titel)]
    puffer_seite = None

    def abschnitt():
        return " > ".join(t for _, t in pfad)

    def neuer_chunk(text, seite, typ="text", bild=""):
        chunks.append({"id": f"pdf_{len(chunks):04d}", "thema": abschnitt(), "text": text,
                       "seite": seite, "typ": typ, "bild": bild})

    def leere_puffer(zwingend=True):
        nonlocal puffer, puffer_seite
        if not puffer:
            return
        text = " ".join(puffer).strip()
        if not zwingend and _woerter(text) < MIN_WOERTER:
            return
        teile, aktuell = [], []
        for satz in _saetze(text):
            if aktuell and _woerter(" ".join(aktuell + [satz])) > ZIEL_WOERTER:
                teile.append(" ".join(aktuell))
                aktuell = []
            aktuell.append(satz)
        if aktuell:
            teile.append(" ".join(aktuell))
        for t in teile:
            neuer_chunk(t, puffer_seite)
        puffer, puffer_seite = [], None

    for e in eintraege:
        typ = e.get("type", "text")
        seite = int(e.get("page_idx", 0)) + 1
        if typ in ("discarded", "header", "footer", "page_number"):
            continue

        if typ == "text" or typ == "list" or (typ not in ("image", "table", "equation") and e.get("text")):
            text = bereinige(e.get("text", "")) if typ != "list" else bereinige(" ".join(e.get("list_items", [])) or e.get("text", ""))
            if not text or re.fullmatch(r"[\d\sIVXivx.\-–]+", text):
                continue  # leere Zeilen, reine Seitenzahlen
            ebene_mineru = e.get("text_level")
            m = _NUMMERIERT.match(text)
            ist_ueberschrift = bool(ebene_mineru) and _woerter(text) <= 15
            if ist_ueberschrift:
                leere_puffer()
                ebene = len(m.group(1).split(".")) if m else 99
                while pfad and pfad[-1][0] >= ebene:
                    pfad.pop()
                pfad.append((ebene, text))
                continue
            if puffer_seite is None:
                puffer_seite = seite
            puffer.append(text)
            if _woerter(" ".join(puffer)) >= ZIEL_WOERTER:
                leere_puffer()
            continue

        if typ == "equation":
            latex = (e.get("text") or "").strip()
            if latex:
                if puffer_seite is None:
                    puffer_seite = seite
                puffer.append(latex if latex.startswith("$") else f"$${latex}$$")
            continue

        if typ == "table":
            leere_puffer()
            titel = _liste(e.get("table_caption"))
            fuss = _liste(e.get("table_footnote"))
            koerper = tabelle_als_text(e.get("table_body", ""))
            zeilen = koerper.splitlines() or [""]
            teil, teile = [], []
            for z in zeilen:
                if teil and _woerter("\n".join(teil + [z])) > TABELLE_MAX_WOERTER:
                    teile.append(teil)
                    teil = []
                teil.append(z)
            teile.append(teil)
            for t in teile:
                text = "\n".join(x for x in [f"Tabelle: {titel}" if titel else "Tabelle", "\n".join(t), fuss] if x)
                neuer_chunk(text.strip(), seite, "tabelle", e.get("img_path", ""))
            continue

        if typ == "image":
            leere_puffer()
            titel = _liste(e.get("image_caption") or e.get("img_caption"))
            fuss = _liste(e.get("image_footnote") or e.get("img_footnote"))
            bild = e.get("img_path", "")
            beschreibung = bildbeschreibungen.get(bild, "") if mit_beschreibungen else ""
            if not (titel or beschreibung):
                continue
            teile = [f"Abbildung: {titel}" if titel else "Abbildung"]
            if fuss:
                teile.append(fuss)
            if beschreibung:
                teile.append(f"Bildbeschreibung (automatisch erzeugt): {beschreibung}")
            neuer_chunk("\n".join(teile), seite, "abbildung", bild)
            continue

    leere_puffer()
    return chunks


def statistik(chunks):
    from collections import Counter
    w = sorted(_woerter(c["text"]) for c in chunks)
    typen = Counter(c["typ"] for c in chunks)
    median = w[len(w) // 2] if w else 0
    return (f"{len(chunks)} Chunks ({', '.join(f'{k} {v}' for k, v in typen.items())}); "
            f"Wörter Median {median}, Min {w[0] if w else 0}, Max {w[-1] if w else 0}")

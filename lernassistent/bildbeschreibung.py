"""
bildbeschreibung.py
-------------------
V7b: Ein kleines Vision-Language-Modell (VLM) beschreibt Abbildungen als Text; der Text
wird wie ein normaler Chunk indiziert. Läuft nur beim Bau der Wissensbasis (offline),
nicht während Lernende das System nutzen.

Vorbild: Saucă & Rusnac (2026): lokales VLM (Qwen2-VL-2B, Qwen2.5-VL-3B etwas besser)
beschreibt Tabellen/Abbildungen auf 8 GB VRAM. Standard hier: qwen2.5vl:3b über Ollama
(kleines Modell aus Sicherheitsgründen: wenig VRAM, weniger Ausfälle über Nacht).

Prompt B-v2 (B-v1 bis zum Pilot): fest und dokumentunabhängig (gleiche Prinzipien wie der Prompt-Satz,
claude/Prompt_Set_Spezifikation.md): nur Sichtbares, Beschriftungen wörtlich, keine Deutung.
Risiko: erfundene Details würden zu "Quellmaterial" -> Beschreibungen werden als
automatisch erzeugt markiert und vor der Nutzung stichprobenartig von Hand geprüft
(Prüfdatei bildbeschreibungen_pruefung.csv).
"""
import base64
import re
import csv
import hashlib
import json
import time
from pathlib import Path

import requests

VLM_MODELL = "qwen2.5vl:7b"  # 13 Oct 2026: 7b statt 3b nach Pilotvergleich (3b erfand Achsen/Bauteile)
BILD_PROMPT_VERSION = "B-v3"
VLM_OPTIONEN = {"temperature": 0, "seed": 42, "num_predict": 300, "repeat_penalty": 1.15}  # Längenbremse gegen Wiederholungsschleifen
MIN_KANTE_PX = 80  # kleinere Bilder (Symbole, Zierelemente) werden übersprungen


def _ollama_url():
    from rag_pipeline import OLLAMA_URL
    return OLLAMA_URL


def bild_prompt(bildunterschrift):
    """B-v3 (13 Oct 2026). Verlauf: B-v1 -> erfundene Bauteile (Rotor, Stator in einem einfachen
    Stromkreis). B-v2 -> Wiederholungsschleife (Beschriftungsliste 100-fach) und erfundene
    Achsen/Kurven bei einer Ersatzschaltung, weil die Achsenregel für jede Abbildung galt.
    B-v3: kurz (2-4 Sätze), Beschriftungen je einmal, Achsen nur bei echten Diagrammen."""
    hinweis = f"\nBildunterschrift (nur zur Orientierung, nicht wiederholen): {bildunterschrift}" if bildunterschrift else ""
    return f"""Beschreibe diese Abbildung aus einem technischen Lehrbuch in 2 bis 4 Sätzen. Gib nur wieder, was eindeutig zu sehen ist.

Erster Satz: Art der Abbildung (zum Beispiel Schaltplan, Ersatzschaltbild, Diagramm mit Achsen, Zeigerdiagramm, Schnittbild, Foto).
Danach: die lesbaren Beschriftungen und Formelzeichen, jede nur einmal.
Nur wenn die Abbildung ein Diagramm mit Achsen ist: welche Größen an den Achsen stehen und wie die Kurven verlaufen.

Erkläre keine Abkürzungen und keine Funktion. Nenne keine Bauteile, die nicht eindeutig erkennbar sind.
Ohne Markdown, ohne LaTeX, höchstens 80 Wörter, auf Deutsch.{hinweis}"""


def saeubere(text, max_woerter=120):
    """Entfernt Markdown/LaTeX-Klammern, schneidet Wiederholungsschleifen ab (eine Wortfolge,
    die sich direkt mehr als zweimal wiederholt) und begrenzt die Länge.
    Rückgabe (text, wiederholung_gefunden)."""
    text = re.sub(r"\\[()\[\]]", "", text)
    text = re.sub(r"[*#`]+", "", text)
    text = re.sub(r"_\{([^{}]*)\}", r"_\1", text)          # R_{thJC} -> R_thJC
    text = re.sub(r"\s*\n\s*[-•]\s*", ", ", text)
    text = re.sub(r"\s*\n\s*", " ", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text).strip()
    w = text.split()
    wiederholung = False
    for k in range(1, 25):
        for i in range(0, max(0, len(w) - 3 * k) + 1):
            if w[i:i + k] == w[i + k:i + 2 * k] == w[i + 2 * k:i + 3 * k]:
                w = w[:i + k]
                wiederholung = True
                break
        if wiederholung:
            break
    if len(w) > max_woerter:
        w = w[:max_woerter]
    text = " ".join(w).rstrip(",;")
    if wiederholung or len(w) == max_woerter:
        ende = max(text.rfind(". "), text.rfind("."))
        text = text[:ende + 1] if ende > len(text) // 2 else text + " …"
    return text, wiederholung


def _bildgroesse(pfad):
    try:
        import pymupdf
        pix = pymupdf.Pixmap(str(pfad))
        return pix.width, pix.height
    except Exception:
        return None


def beschreibe(pfad, bildunterschrift="", modell=VLM_MODELL, timeout=300):
    with open(pfad, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    payload = {"model": modell, "prompt": bild_prompt(bildunterschrift), "images": [b64],
               "stream": False, "options": VLM_OPTIONEN}
    r = requests.post(_ollama_url(), json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json().get("response", "").strip()


def beschreibe_alle(eintraege, bildordner, cache_datei, modell=VLM_MODELL, max_bilder=None):
    """Beschreibt alle Abbildungen aus der MinerU-content_list. Fortsetzbar: bereits
    beschriebene Bilder (Cache-JSON) werden übersprungen. Rückgabe {img_path: beschreibung}."""
    cache_datei = Path(cache_datei)
    cache = json.loads(cache_datei.read_text(encoding="utf-8")) if cache_datei.exists() else {}
    from pdf_struktur import ist_abbildung, bildunterschrift
    bilder = [e for e in eintraege if ist_abbildung(e)]
    if max_bilder:
        bilder = bilder[:max_bilder]
    print(f"{len(bilder)} Abbildungen, {len(cache)} bereits beschrieben (Cache), Modell {modell}", flush=True)
    for n, e in enumerate(bilder, 1):
        rel = e["img_path"]
        alt = cache.get(rel)
        if alt and (alt.get("grund") == "zu_klein" or
                    (alt.get("prompt_version") == BILD_PROMPT_VERSION and alt.get("modell") == modell)):
            continue
        pfad = Path(bildordner) / rel
        groesse = _bildgroesse(pfad)
        unterschrift = bildunterschrift(e)
        if groesse and min(groesse) < MIN_KANTE_PX:
            cache[rel] = {"beschreibung": "", "grund": "zu_klein", "seite": e.get("page_idx", 0) + 1}
            continue
        t0 = time.time()
        try:
            roh = beschreibe(pfad, unterschrift, modell)
            text, schleife = saeubere(roh)
            cache[rel] = {"beschreibung": text, "wiederholung": schleife, "roh_woerter": len(roh.split()), "sekunden": round(time.time() - t0, 1),
                          "seite": e.get("page_idx", 0) + 1, "bildunterschrift": unterschrift,
                          "modell": modell, "prompt_version": BILD_PROMPT_VERSION,
                          "sha1": hashlib.sha1(pfad.read_bytes()).hexdigest()[:12]}
        except Exception as ex:
            print(f"  [{n}] FEHLER {rel}: {ex}", flush=True)
            continue
        if n % 10 == 0 or n == len(bilder):
            cache_datei.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  {n}/{len(bilder)} beschrieben ({cache[rel]['sekunden']} s zuletzt)", flush=True)
    cache_datei.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return {k: v.get("beschreibung", "") for k, v in cache.items()}


def schreibe_pruefdatei(cache_datei, ziel, stichprobe=30, seed=0):
    """Zufallsstichprobe für die Handprüfung (Spalte bewertung: ok / fehler / erfunden)."""
    import random
    cache = json.loads(Path(cache_datei).read_text(encoding="utf-8"))
    eintraege = [(k, v) for k, v in cache.items() if v.get("beschreibung")]
    random.Random(seed).shuffle(eintraege)
    with open(ziel, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["bild", "seite", "bildunterschrift", "beschreibung", "bewertung", "anmerkung"])
        for k, v in eintraege[:stichprobe]:
            w.writerow([k, v.get("seite", ""), v.get("bildunterschrift", ""), v["beschreibung"], "", ""])

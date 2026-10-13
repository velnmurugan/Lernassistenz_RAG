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

VLM_MODELL = "qwen2.5vl:3b"
BILD_PROMPT_VERSION = "B-v2"
VLM_OPTIONEN = {"temperature": 0, "seed": 42}
MIN_KANTE_PX = 80  # kleinere Bilder (Symbole, Zierelemente) werden übersprungen


def _ollama_url():
    from rag_pipeline import OLLAMA_URL
    return OLLAMA_URL


def bild_prompt(bildunterschrift):
    """B-v2 (13 Oct 2026). Änderung gegenüber B-v1 nach dem Pilot: qwen2.5vl:3b hat Bauteile und
    Bedeutungen erfunden (Rotor, Stator, Transformator in einem einfachen Stromkreis) und
    Abkürzungen gedeutet. B-v2 verlangt Art + wörtliche Beschriftungen + bei Diagrammen Achsen
    und Verlauf, verbietet Deutungen und Abkürzungserklärungen und lässt Unsicheres weg."""
    hinweis = f"\nBildunterschrift (nur zur Orientierung, nicht wiederholen): {bildunterschrift}" if bildunterschrift else ""
    return f"""Beschreibe diese Abbildung aus einem Lehrbuch. Gib nur wieder, was eindeutig zu sehen ist.

1. Art der Abbildung in einem Satz (zum Beispiel Schaltplan, Diagramm, Kennlinie, Zeigerdiagramm, Schnittbild, Foto, Tabelle).
2. Alle lesbaren Beschriftungen, Formelzeichen, Zahlen und Einheiten wörtlich.
3. Bei Diagrammen: welche Größe auf welcher Achse steht (mit Einheit) und wie die Kurven verlaufen (steigt, fällt, Maximum, Schnittpunkt).
4. Erkläre keine Abkürzungen und keine Funktion. Nenne keine Bauteile, die nicht eindeutig erkennbar sind. Was unsicher ist, lässt du weg.

Antworte als Fließtext ohne Aufzählungszeichen und ohne Markdown, höchstens 100 Wörter, auf Deutsch.{hinweis}"""


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
    text = r.json().get("response", "").strip()
    text = re.sub(r"[*#`]+", "", text)                  # Markdown entfernen
    return re.sub(r"\s*\n\s*[-•]\s*", "; ", text).strip()


def beschreibe_alle(eintraege, bildordner, cache_datei, modell=VLM_MODELL, max_bilder=None):
    """Beschreibt alle Abbildungen aus der MinerU-content_list. Fortsetzbar: bereits
    beschriebene Bilder (Cache-JSON) werden übersprungen. Rückgabe {img_path: beschreibung}."""
    cache_datei = Path(cache_datei)
    cache = json.loads(cache_datei.read_text(encoding="utf-8")) if cache_datei.exists() else {}
    bilder = [e for e in eintraege if e.get("type") == "image" and e.get("img_path")]
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
        unterschrift = " ".join(e.get("image_caption") or e.get("img_caption") or [])
        if groesse and min(groesse) < MIN_KANTE_PX:
            cache[rel] = {"beschreibung": "", "grund": "zu_klein", "seite": e.get("page_idx", 0) + 1}
            continue
        t0 = time.time()
        try:
            text = beschreibe(pfad, unterschrift, modell)
            cache[rel] = {"beschreibung": text, "sekunden": round(time.time() - t0, 1),
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

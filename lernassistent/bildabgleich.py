"""
bildabgleich.py
---------------
BA-v1: ordnet ein hochgeladenes Bild einer Abbildung der Wissensbasis zu (ORB-Merkmale + RANSAC-Homographie, OpenCV),
ohne dass das Sprachmodell das Bild erkennen muss. Die Wissensbasis enthält 'abbildung'-Chunks mit Bildunterschrift, Abschnittspfad (Thema),
Seite und Bilddatei. Treffer (>= MIN_INLIER Inlier) liefern Thema und Bildunterschrift für die Suche und als Fundstelle in der Frage.

Standard: aus. Einschalten mit LERNASSISTENT_BILDABGLEICH=1.
Benötigt opencv-python(-headless) und die extrahierten Buchbilder unter daten/extraktion (LERNASSISTENT_BILDWURZEL). Fehlt etwas, bleibt
die Funktion still aus (kein Fehler für Lernende). Die Merkmale werden einmal berechnet und in evaluationsdaten/bildabgleich_cache.pkl gehalten.
"""
import json
import os
import pickle
from pathlib import Path

ENDUNGEN = (".png", ".jpg", ".jpeg", ".webp")
MAX_KANTE = 900
MIN_INLIER = int(os.environ.get("LERNASSISTENT_BILDABGLEICH_MIN", "15"))
BILDWURZEL = os.environ.get("LERNASSISTENT_BILDWURZEL", "daten/extraktion")
CACHE = Path("evaluationsdaten") / "bildabgleich_cache.pkl"
KB_PFAD = None  # setzt die App (Pfad der aktiven Wissensbasis)
_INDEX = {}


def aktiv():
    return os.environ.get("LERNASSISTENT_BILDABGLEICH", "") == "1"


def _cv():
    import cv2
    import numpy as np
    return cv2, np


def lade_grau(daten=None, pfad=None):
    cv2, np = _cv()
    roh = np.frombuffer(daten, dtype=np.uint8) if daten is not None else np.fromfile(str(pfad), dtype=np.uint8)
    img = cv2.imdecode(roh, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    h, w = img.shape
    s = MAX_KANTE / max(h, w)
    return cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA) if s < 1 else img


def dhash(img, n=8):
    cv2, _ = _cv()
    k = cv2.resize(img, (n + 1, n), interpolation=cv2.INTER_AREA)
    return int("".join("1" if b else "0" for b in (k[:, 1:] > k[:, :-1]).flatten()), 2)


def merkmale(img, orb=None):
    cv2, _ = _cv()
    orb = orb or cv2.ORB_create(nfeatures=1000)
    kp, des = orb.detectAndCompute(img, None)
    return [(p.pt[0], p.pt[1]) for p in kp], des


def inlier(q, k, bf=None):
    cv2, np = _cv()
    bf = bf or cv2.BFMatcher(cv2.NORM_HAMMING)
    (kq, dq), (kk, dk) = q, k
    if dq is None or dk is None or len(kq) < 8 or len(kk) < 8:
        return 0
    paare = bf.knnMatch(dq, dk, k=2)
    gut = [m for m, n in (p for p in paare if len(p) == 2) if m.distance < 0.75 * n.distance]
    if len(gut) < 8:
        return len(gut) // 4
    a = np.float32([kq[m.queryIdx] for m in gut]).reshape(-1, 1, 2)
    b = np.float32([kk[m.trainIdx] for m in gut]).reshape(-1, 1, 2)
    _, maske = cv2.findHomography(a, b, cv2.RANSAC, 5.0)
    return int(maske.sum()) if maske is not None else 0


def baue_index(kb_pfad, bildwurzel=None, cache_pfad=None):
    """Liste (chunk, (merkmale, dhash)) aller Abbildungs-Chunks mit auffindbarer Bilddatei. Wirft ImportError ohne OpenCV."""
    cv2, _ = _cv()
    chunks = json.load(open(kb_pfad, encoding="utf-8"))["chunks"]
    abb = [c for c in chunks if c.get("typ") == "abbildung" and c.get("bild")]
    dateien = {}
    for p in Path(bildwurzel or BILDWURZEL).rglob("*"):
        if p.suffix.lower() in ENDUNGEN:
            dateien.setdefault(p.name, p)
    cache_pfad = Path(cache_pfad or CACHE)
    cache = {}
    if cache_pfad.exists():
        try:
            cache = pickle.load(open(cache_pfad, "rb"))
        except Exception:
            cache = {}
    orb = cv2.ORB_create(nfeatures=1000)
    index, neu = [], False
    for c in abb:
        name = Path(c["bild"]).name
        p = dateien.get(name)
        if not p:
            continue
        if name not in cache:
            img = lade_grau(pfad=p)
            if img is None:
                continue
            cache[name] = (merkmale(img, orb), dhash(img))
            neu = True
        index.append((c, cache[name]))
    if neu:
        cache_pfad.parent.mkdir(exist_ok=True)
        pickle.dump(cache, open(cache_pfad, "wb"))
    return index


def finde(daten, index, min_inlier=None):
    """Bild (bytes) -> {'chunk', 'inlier', 'rang2'} des besten Treffers oder None (zu wenige Inlier oder kein Bild)."""
    cv2, _ = _cv()
    img = lade_grau(daten=daten)
    if img is None or not index:
        return None
    q = merkmale(img)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    erg = sorted(((inlier(q, m, bf), c) for c, (m, h) in index), key=lambda x: -x[0])
    if not erg or erg[0][0] < (min_inlier or MIN_INLIER):
        return None
    return {"chunk": erg[0][1], "inlier": erg[0][0], "rang2": erg[1][0] if len(erg) > 1 else 0}


def index_fuer_app():
    """Index der aktiven Wissensbasis (einmal je Prozess); None, wenn aus oder nicht möglich."""
    if not aktiv() or not KB_PFAD:
        return None
    if KB_PFAD not in _INDEX:
        try:
            _INDEX[KB_PFAD] = baue_index(KB_PFAD)
        except Exception as e:
            print(f"WARNUNG Bildabgleich nicht verfügbar: {e}")
            _INDEX[KB_PFAD] = []
    return _INDEX[KB_PFAD] or None


def fundstelle(treffer):
    """Text für Suche/Frage aus einem Treffer: (suchtext, fundstelle_satz)."""
    c = treffer["chunk"]
    unterschrift = (c.get("text", "").split("\n")[0]).replace("Abbildung:", "").strip()
    thema = (c.get("thema") or "").strip()
    such = " ".join(x for x in (thema.replace(">", " "), unterschrift) if x)
    satz = f"Fundstelle der Abbildung im Lernmaterial (automatisch zugeordnet): Abschnitt „{thema}“, Seite {c.get('seite', '?')}, Bildunterschrift „{unterschrift}“."
    return such, satz

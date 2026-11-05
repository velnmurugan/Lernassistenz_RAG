"""
reranker.py
-----------
V3: Cross-Encoder-Reranking der Retrieval-Kandidaten.

Zweistufiges Retrieval (Kandidaten holen -> genauer neu ordnen):
  1. Die bisherige Pipeline (z. B. "hybrid_kg", V2) liefert eine Rangliste.
  2. Die besten RERANK_KANDIDATEN Chunks werden von einem Cross-Encoder neu
     bewertet: Er liest Frage und Chunk ZUSAMMEN (statt zwei getrennte Vektoren
     zu vergleichen) und gibt einen Relevanzwert aus.
  3. Die Top-4 nach diesem Wert gehen an qwen.

Warum: Dense/BM25/Graph vergleichen nur Wörter bzw. getrennte Vektoren. Der
Cross-Encoder sieht, ob der Chunk die Frage tatsächlich beantwortet — erwartet
hilfreich bei (a) "Warum…/Was macht…"-Fragen, deren Wortlaut nicht zum Chunk
passt (Q5, Q12, Q16: Rang 81–147 in V2), und (b) Fehltreffern wie pdf_11116
(Dämpfungsmaß "D"), die dense nur wegen des Buchstabens "D" auf Rang 1 setzt.

Quellen: Nogueira & Cho (2019), Passage Re-ranking with BERT (Cross-Encoder-
Reranking); zweistufiges Retrieval mit Reranker: Oche et al. (2025, S. 6);
lokales Vorbild auf 8 GB: Saucă & Rusnac (2026) (RRF -> Cross-Encoder -> Top 3).
Gegenbefund: LLM-basiertes Reranking verschlechterte Ergebnisse bei Chen et al.
(2025) -> hier bewusst ein kleiner, spezialisierter Cross-Encoder statt qwen.

Modelle (mehrsprachig, weil das Material deutsch ist):
  "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"  ~118 Mio. Parameter, schnell auf CPU,
      trainiert auf mMARCO (MS MARCO maschinell übersetzt, u. a. Deutsch;
      Bonifacio et al. 2021)
  "BAAI/bge-reranker-v2-m3"                      ~568 Mio. Parameter, stärker, langsamer
      (Basis BGE-M3, Chen et al. 2024)
Welches besser ist, wird mit retrieval_vergleich.py --reranker … entschieden.

GERÄT: Standard "cpu". qwen3.5:9b belegt in Ollama ~7,2 von 8 GB VRAM; ein
Reranker auf der GPU könnte daneben keinen Speicher mehr bekommen.
"""
import re

# Entscheidung V3 (retrieval_vergleich.py, 25 Testfragen, Vorstufe hybrid_kg k=5):
#   MiniLM, 30 Kandidaten: R@4 17, R@4+Nb 21, MRR 0.450, +0.9 s/Frage (CPU)
#   bge,    30 Kandidaten: R@4 18, R@4+Nb 21, MRR 0.534, +7.7 s/Frage
#   MiniLM, 50 Kandidaten: R@4 17, R@4+Nb 20, MRR 0.487, +1.5 s/Frage
#   bge,    50 Kandidaten: R@4 20, R@4+Nb 23, MRR 0.592, +12.7 s/Frage  <- gewählt
# Mit 50 Kandidaten erreicht der Reranker Q18 (Rang 40) und Q20 (Zweihandverriegelung,
# Rang 39). Das schwächere MiniLM profitiert davon nicht (mehr Störkandidaten).
# Preis: ~13 s zusätzliche Wartezeit pro Frage auf der CPU (offener Punkt für die Studien-App).
RERANKER_MODELL = "BAAI/bge-reranker-v2-m3"
RERANK_KANDIDATEN = 50   # so viele Chunks aus der Vorstufe werden neu bewertet
RERANKER_GERAET = "cpu"  # "cpu" | "cuda"
RERANKER_MAX_LAENGE = 512

_modelle = {}


def parameter():
    """Für lauf_<ID>.json (Reproduzierbarkeit)."""
    return {"reranker_modell": RERANKER_MODELL, "rerank_kandidaten": RERANK_KANDIDATEN,
            "reranker_geraet": RERANKER_GERAET, "reranker_max_laenge": RERANKER_MAX_LAENGE}


def _lade():
    schluessel = (RERANKER_MODELL, RERANKER_GERAET)
    if schluessel not in _modelle:
        from sentence_transformers import CrossEncoder
        _modelle[schluessel] = CrossEncoder(RERANKER_MODELL, max_length=RERANKER_MAX_LAENGE,
                                            device=RERANKER_GERAET)
    return _modelle[schluessel]


def _bereinige(text):
    """Silbentrennung aus der PDF-Extraktion zusammenführen, Zeilenumbrüche glätten
    (gleiche Regel wie rag_pipeline.tokenisiere)."""
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip()


import os as _os21, threading as _th21, time as _t21  # V21-S
_RR_GPU = _os21.environ.get("LERNASSISTENT_RR_GPU") == "1"
GPU_SPERRE = _th21.RLock()  # V21-S: Reranker und Sprachmodell nie gleichzeitig auf der GPU
GPU_PROTOKOLL = []  # V21-S: (Sekunden, "gpu" | "cpu-rueckfall") je Aufruf


def _ollama_entladen():
    """V21-S: alle geladenen Ollama-Modelle aus der GPU nehmen (keep_alive 0) und warten, bis sie weg sind."""
    import requests
    import rag_pipeline as _rp
    ps = _rp.OLLAMA_URL.replace("/api/generate", "/api/ps")
    try:
        for m in requests.get(ps, timeout=5).json().get("models", []):
            requests.post(_rp.OLLAMA_URL, json={"model": m["name"], "keep_alive": 0}, timeout=60)
        for _ in range(80):
            if not requests.get(ps, timeout=5).json().get("models"):
                return True
            _t21.sleep(0.25)
    except Exception as e:
        print(f"WARNUNG V21-S Ollama entladen: {e}")
    return False


def _bewerte_gpu(paare):
    """V21-S: dieselbe Bewertung wie auf der CPU, gerechnet auf der GPU (fp32, gleiches Modell)."""
    import torch
    import torch.nn as nn
    modell = _lade()  # geladen auf RERANKER_GERAET ("cpu")
    netz = modell if isinstance(modell, nn.Module) else modell.model
    t, art = _t21.perf_counter(), "gpu"
    z = {}  # V21-S: Teilzeiten (Terminal)
    with GPU_SPERRE:
        z["warten"] = _t21.perf_counter() - t
        try:
            if not torch.cuda.is_available():
                raise RuntimeError("keine GPU")
            t1 = _t21.perf_counter()
            if not _ollama_entladen():
                raise RuntimeError("Ollama-Modell nicht entladen")
            z["entladen"] = _t21.perf_counter() - t1
            t1 = _t21.perf_counter()
            netz.to("cuda")
            if not isinstance(modell, nn.Module) and hasattr(modell, "_target_device"):  # nur alte sentence-transformers
                modell._target_device = torch.device("cuda")
            torch.cuda.synchronize()
            z["zur_gpu"] = _t21.perf_counter() - t1
            t1 = _t21.perf_counter()
            werte = modell.predict(paare, batch_size=16, show_progress_bar=False)
            torch.cuda.synchronize()
            z["rechnen"] = _t21.perf_counter() - t1
        except Exception as e:
            print(f"WARNUNG V21-S Reranker auf GPU nicht möglich ({e}) – CPU wie V20")
            art = "cpu-rueckfall"
            netz.to("cpu")
            if not isinstance(modell, nn.Module) and hasattr(modell, "_target_device"):  # nur alte sentence-transformers
                modell._target_device = torch.device("cpu")
            torch.cuda.empty_cache() if torch.cuda.is_available() else None
            werte = modell.predict(paare, batch_size=16, show_progress_bar=False)
        finally:
            t1 = _t21.perf_counter()
            netz.to("cpu")
            if not isinstance(modell, nn.Module) and hasattr(modell, "_target_device"):  # nur alte sentence-transformers
                modell._target_device = torch.device("cpu")
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            z["zurueck"] = _t21.perf_counter() - t1
    GPU_PROTOKOLL.append((round(_t21.perf_counter() - t, 2), art))
    print(f"V21-S Reranker {art}: gesamt {_t21.perf_counter() - t:.1f} s | "
          + " | ".join(f"{k} {v:.1f} s" for k, v in z.items()), flush=True)
    return werte


def bewerte(frage, texte):
    """Relevanzwert je Text (höher = relevanter). Reihenfolge wie texte."""
    if not texte:
        return []
    paare = [(frage, _bereinige(t)) for t in texte]
    if _RR_GPU:  # V21-S
        return [float(w) for w in _bewerte_gpu(paare)]
    werte = _lade().predict(paare, batch_size=16, show_progress_bar=False)
    return [float(w) for w in werte]
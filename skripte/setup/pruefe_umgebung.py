"""
pruefe_umgebung.py
------------------
Prüft vor dem Nachtlauf, ob alles bereit ist. Am Ende steht ALLES OK oder eine Liste der Probleme.

Start:  python skripte/setup/pruefe_umgebung.py
"""
import sys as _sys, pathlib as _pl  # Projektpfade (lernassistent/pfadsetup.py)
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import importlib
import shutil
import subprocess
from pathlib import Path

import requests

PROBLEME = []


def ok(text):
    print(f"  OK    {text}")


def fehler(text):
    print(f"  FEHLT {text}")
    PROBLEME.append(text)


def main():
    print("Python-Pakete (Projektumgebung):")
    for m in ("numpy", "sklearn", "rank_bm25", "snowballstemmer", "sentence_transformers", "pypdf", "pymupdf", "requests"):
        try:
            importlib.import_module(m)
            ok(m)
        except Exception:
            fehler(f"Paket {m}  ->  pip install {'pymupdf' if m == 'pymupdf' else m}")

    print("MinerU (eigene conda-Umgebung 'mineru'):")
    import pdf_struktur as ps
    try:
        r = subprocess.run(ps.MINERU_BEFEHL + ["--version"], capture_output=True, text=True, timeout=180)
        (ok if r.returncode == 0 else fehler)(f"MinerU: {(r.stdout or r.stderr).strip()[:80]}")
    except Exception as ex:
        fehler(f"MinerU nicht aufrufbar ({ex})")

    print("Ollama und Modelle:")
    import rag_pipeline as rp
    import bildbeschreibung as bb
    try:
        tags = requests.get(rp.OLLAMA_URL.replace("/api/generate", "/api/tags"), timeout=5).json()
        namen = {m["name"] for m in tags.get("models", [])}
        for modell in (rp.MODEL_NAME, "mistral-nemo:latest", bb.VLM_MODELL):
            vorhanden = modell in namen or f"{modell}:latest" in namen
            (ok if vorhanden else fehler)(f"Modell {modell}" + ("" if vorhanden else f"  ->  ollama pull {modell}"))
    except Exception as ex:
        fehler(f"Ollama nicht erreichbar ({ex})")

    print("Dateien:")
    for p in ("daten/wissensbasen/knowledge_base_boege.json", "daten/testfragen/testfragen_v1.csv",
              "daten/testfragen/testfragen_fischer_v1.csv"):
        (ok if Path(p).exists() else fehler)(p)
    pdfs = list(Path("daten/quellen/fischer").glob("*.pdf"))
    (ok if pdfs else fehler)(f"Fischer-PDF in daten/quellen/fischer/ ({pdfs[0].name if pdfs else 'keine'})")

    print("GPU und Speicher:")
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=10)
        belegt, gesamt = [int(x) for x in r.stdout.strip().split(",")]
        (ok if belegt < 1500 else fehler)(f"GPU-Speicher belegt {belegt}/{gesamt} MB"
                                         + ("" if belegt < 1500 else "  ->  ollama stop <modell>"))
    except Exception as ex:
        fehler(f"nvidia-smi ({ex})")
    frei = shutil.disk_usage(".").free / 1e9
    (ok if frei > 15 else fehler)(f"freier Plattenplatz {frei:.0f} GB (mind. 15 GB)")

    print("\nALLES OK" if not PROBLEME else f"\n{len(PROBLEME)} PROBLEM(E):\n- " + "\n- ".join(PROBLEME))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# Projektstand als ZIP sammeln (nur Python-Standardbibliothek, laeuft im Vordergrund).
# Aufruf im Projektordner (dort, wo rag_pipeline.py liegt):
#     python3 projekt_status_zip.py
# Laufzeit: ca. 10-60 Sekunden. Ergebnis: projekt_status_<Zeitstempel>.zip
# (wird zusaetzlich nach Windows-Downloads kopiert, falls gefunden).
import os, sys, glob, time, shutil, zipfile, subprocess, platform

WURZEL = os.getcwd()
ZEIT = time.strftime("%Y%m%d_%H%M%S")
ZIELNAME = f"projekt_status_{ZEIT}.zip"
ZIEL = os.path.join(WURZEL, ZIELNAME)

MAX_DATEI = 3 * 1024 * 1024        # Dateien > 3 MB werden nur aufgelistet
MAX_GESAMT = 150 * 1024 * 1024     # Warnschwelle fuer das ZIP

AUSSCHLUSS_ORDNER = {
    ".git", ".venv", "venv", "env", "__pycache__", "node_modules",
    ".ipynb_checkpoints", ".cache", ".mypy_cache", ".pytest_cache",
    "chroma", "chroma_db", "faiss_index", "vectorstore", "vektorstore",
}
AUSSCHLUSS_ENDUNG = (
    ".pyc", ".zip", ".gz", ".tar", ".7z", ".bin", ".pt", ".pth", ".safetensors",
    ".gguf", ".faiss", ".sqlite3", ".db", ".npy", ".npz", ".pkl", ".parquet",
    ".mp4", ".mov", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".docx", ".pptx", ".xlsx",
)
# Bilder/PDF/Office werden nicht eingepackt, aber in der Dateiliste aufgefuehrt.
GEHEIM_TEILE = (".env", "secret", "token", "apikey", "api_key", "password", "passwort", "id_rsa")


def lauf(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (r.stdout + (("\n[stderr] " + r.stderr) if r.stderr.strip() else "")).strip()
    except Exception as e:
        return f"[nicht verfuegbar: {e}]"


def ist_geheim(name):
    n = name.lower()
    return any(t in n for t in GEHEIM_TEILE)


def sammle():
    ein, skip_gross, skip_typ, skip_geheim = [], [], [], []
    alle = []
    for ordner, dirs, dateien in os.walk(WURZEL):
        dirs[:] = [d for d in dirs if d not in AUSSCHLUSS_ORDNER]
        for f in dateien:
            voll = os.path.join(ordner, f)
            rel = os.path.relpath(voll, WURZEL)
            if f.startswith("projekt_status_") and f.endswith(".zip"):
                continue
            try:
                gr = os.path.getsize(voll)
            except OSError:
                continue
            alle.append((rel, gr))
            if ist_geheim(f):
                skip_geheim.append(rel)
            elif f.lower().endswith(AUSSCHLUSS_ENDUNG):
                skip_typ.append((rel, gr))
            elif gr > MAX_DATEI:
                skip_gross.append((rel, gr))
            else:
                ein.append((rel, gr))
    return ein, skip_gross, skip_typ, skip_geheim, alle


def status_text(ein, skip_gross, skip_typ, skip_geheim, alle):
    z = []
    z.append(f"Projektstand {time.strftime('%Y-%m-%d %H:%M:%S')}")
    z.append(f"Ordner: {WURZEL}")
    z.append(f"Python: {sys.version.split()[0]} | {platform.platform()}")
    z.append("")
    z.append("== Git ==")
    z.append(lauf("git status --short | head -50"))
    z.append("-- letzte Commits --")
    z.append(lauf("git log --oneline -25"))
    z.append("-- Tags --")
    z.append(lauf("git tag --sort=-creatordate | head -25"))
    z.append("-- Branch --")
    z.append(lauf("git rev-parse --abbrev-ref HEAD"))
    z.append("")
    z.append("== Ollama ==")
    z.append(lauf("ollama list"))
    z.append("")
    z.append("== GPU / RAM ==")
    z.append(lauf("nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv"))
    z.append(lauf("free -h"))
    z.append("")
    z.append("== Umgebungsvariablen LERNASSISTENT_* ==")
    ev = [f"{k}={v}" for k, v in sorted(os.environ.items()) if k.startswith("LERNASSISTENT_")]
    z.append("\n".join(ev) if ev else "(keine gesetzt)")
    z.append("")
    z.append("== Python-Pakete (Auszug) ==")
    z.append(lauf("pip list 2>/dev/null | grep -i -E 'chroma|faiss|sentence|transformers|torch|ragas|langchain|requests|numpy|pandas|scikit|rank|bm25|streamlit|gradio|flask|fastapi|mineru|pymupdf|docx' "))
    z.append("")
    z.append("== Zeilenzahl wichtiger Skripte ==")
    for rel, _ in sorted(ein):
        if rel.endswith(".py") and rel.count(os.sep) <= 2:
            try:
                with open(os.path.join(WURZEL, rel), "rb") as fh:
                    z.append(f"{sum(1 for _ in fh):6d}  {rel}")
            except OSError:
                pass
    z.append("")
    z.append(f"== Eingepackt: {len(ein)} Dateien, {sum(g for _, g in ein)/1e6:.1f} MB ==")
    z.append(f"== Nicht eingepackt (zu gross > {MAX_DATEI//1024//1024} MB): {len(skip_gross)} ==")
    for rel, g in sorted(skip_gross):
        z.append(f"  {g/1e6:8.1f} MB  {rel}")
    z.append(f"== Nicht eingepackt (Typ: Bild/PDF/Office/Index/Archiv): {len(skip_typ)} ==")
    for rel, g in sorted(skip_typ)[:400]:
        z.append(f"  {g/1e6:8.2f} MB  {rel}")
    if len(skip_typ) > 400:
        z.append(f"  ... und {len(skip_typ)-400} weitere")
    z.append(f"== Nicht eingepackt (moegliche Zugangsdaten, Name enthaelt Schluesselwort): {len(skip_geheim)} ==")
    for rel in sorted(skip_geheim):
        z.append(f"  {rel}")
    z.append("")
    z.append("== Dateibaum (alle Dateien, Groesse in KB) ==")
    for rel, g in sorted(alle)[:3000]:
        z.append(f"{g/1024:10.1f}  {rel}")
    return "\n".join(z) + "\n"


def windows_downloads():
    kandidaten = glob.glob("/mnt/c/Users/*/Downloads")
    kandidaten = [k for k in kandidaten if not any(x in k for x in ("Public", "Default", "All Users"))]
    return kandidaten[0] if kandidaten else None


def main():
    if not os.path.exists(os.path.join(WURZEL, "rag_pipeline.py")):
        print(f"Hinweis: rag_pipeline.py liegt nicht in {WURZEL}. Im Projektordner starten.")
    print("Sammle Dateien ...")
    ein, skip_gross, skip_typ, skip_geheim, alle = sammle()
    status = status_text(ein, skip_gross, skip_typ, skip_geheim, alle)
    print(f"Packe {len(ein)} Dateien ...")
    with zipfile.ZipFile(ZIEL, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.writestr("STATUS.txt", status)
        for rel, _ in ein:
            try:
                zf.write(os.path.join(WURZEL, rel), arcname=rel)
            except OSError as e:
                print(f"  uebersprungen: {rel} ({e})")
    gr = os.path.getsize(ZIEL)
    print(f"Fertig: {ZIEL} ({gr/1e6:.1f} MB)")
    if gr > MAX_GESAMT:
        print("Warnung: ZIP ist gross. STATUS.txt zeigt, was den Platz braucht.")
    dl = windows_downloads()
    if dl:
        try:
            shutil.copy2(ZIEL, os.path.join(dl, ZIELNAME))
            print(f"Kopiert nach: {dl}")
        except OSError as e:
            print(f"Kopieren nach Downloads fehlgeschlagen: {e}")
    else:
        print("Windows-Downloads nicht gefunden; ZIP liegt im Projektordner.")


if __name__ == "__main__":
    main()

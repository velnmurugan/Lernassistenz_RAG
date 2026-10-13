"""
baue_zweite_wissensbasis.py
---------------------------
Baut eine ZWEITE Wissensbasis (z. B. Fischer, Elektrotechnik) mit genau denselben
Chunking-Einstellungen wie die erste, ohne knowledge_base.json zu überschreiben.
Nutzt dein vorhandenes baue_wissensbasis.py und ersetzt nur Quellordner und Zieldatei.

Start:
  python skripte/wissensbasis/baue_zweite_wissensbasis.py daten/quellen/fischer \
         daten/wissensbasen/knowledge_base_fischer.json

⚠ Die erzeugte JSON enthält den Buchtext (urheberrechtlich geschützt) -> nicht ins Git
  (Muster knowledge_base*.json in .gitignore).
"""
import sys as _sys, pathlib as _pl  # Projektpfade (lernassistent/pfadsetup.py)
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import sys
from pathlib import Path

import baue_wissensbasis as bw


def main():
    if len(sys.argv) != 3:
        sys.exit("Aufruf: python baue_zweite_wissensbasis.py <Quellordner> <Zieldatei.json>")
    quelle, ziel = Path(sys.argv[1]), Path(sys.argv[2])
    if ziel.resolve() == Path("daten/wissensbasen/knowledge_base_boege.json").resolve():
        sys.exit("Zieldatei darf nicht knowledge_base.json sein (würde die erste Wissensbasis überschreiben).")
    if not quelle.is_dir() or not list(quelle.glob("*.pdf")):
        sys.exit(f"Keine PDF in {quelle}/ gefunden.")
    bw.QUELLORDNER = quelle
    bw.ZIEL_DATEI = ziel
    bw.main()


if __name__ == "__main__":
    main()

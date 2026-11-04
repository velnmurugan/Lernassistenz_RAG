"""V20 / G-v6: zwei neue Lösungsregeln (L8 rechnen, wenn alle Werte in der Frage stehen; L9 jede Teilfrage beantworten).
Idempotent; hängt einen Block an lernassistent/rag_pipeline.py an. G-v1 … G-v5 bleiben unverändert.
Aufruf: python patch_v20.py [pfad/zu/lernassistent/rag_pipeline.py]"""
import sys, shutil, hashlib
from pathlib import Path
p = Path(sys.argv[1] if len(sys.argv) > 1 else "lernassistent/rag_pipeline.py")
MARKE = "# === V20 (G-v6) ==="
BLOCK = MARKE + '''
# G-v6 = G-v5 + L8 (rechnen, wenn alle Werte in der Frage stehen; Grundgleichung erlaubt und gekennzeichnet)
#              + L9 (mehrteilige Fragen: jede Teilfrage, alle Ergebnisse im ersten Satz).
# Anlass: Eval300-V4 (Rechenfragen mit RAG): Teilfragen ohne Antwort, "kann nicht berechnet werden" trotz
# vollständiger Angaben. Allgemeine Regeln ohne Beispiele (P1). Nur mit LERNASSISTENT_G=G-v6.
SCAFFOLDING_MARKER_VERSIONEN["G-v6"] = {"hinweis": "HINWEIS:", "loesung": "LÖSUNG:"}
_HINWEIS_REGELN["G-v6"] = _HINWEIS_REGELN["G-v2"]
_HINWEIS_REGELNUMMERN["G-v6"] = "H1 bis H6"
_LOESUNGS_REGELN["G-v6"] = _LOESUNGS_REGELN["G-v5"] + """
L8 Stehen alle Zahlenwerte, die für die gefragten Größen nötig sind, in der Frage, dann rechne die Größen aus.
   Steht die nötige Formel nicht im Lernmaterial, verwende eine allgemein gültige Grundgleichung der Physik oder
   Technik und kennzeichne sie mit „(Grundgleichung, nicht aus dem Lernmaterial)“. Schreibe nie, dass ein Wert
   fehlt, der in der Frage steht.
L9 Besteht die Frage aus mehreren Teilfragen, beantworte jede Teilfrage der Reihe nach und nenne im ersten Satz
   alle gefragten Ergebnisse."""
_LOESUNGS_REGELNUMMERN["G-v6"] = "L1 bis L9"


def _prompt_g_v6(frage, ausgewaehlte_chunks):
    """V20: G-v6 = G-v5 + L8, L9. Nur mit LERNASSISTENT_G=G-v6."""
    return _prompt_g("G-v6", frage, ausgewaehlte_chunks)


_PROMPTS["G-v6"] = _prompt_g_v6
'''
t = p.read_text(encoding="utf-8")
if MARKE in t:
    print("V20 schon eingespielt:", p); sys.exit(0)
for anker in ("_LOESUNGS_REGELN[\"G-v5\"]", "_PROMPTS = {", "def _prompt_g(version, frage, ausgewaehlte_chunks):", "SCAFFOLDING_MARKER_VERSIONEN = {"):
    if anker not in t:
        sys.exit(f"FEHLER: Anker fehlt ({anker}) – unerwarteter Stand, nichts geändert.")
shutil.copy2(p, p.with_name(p.name + ".vor_v20"))
p.write_text(t.rstrip("\n") + "\n\n\n" + BLOCK, encoding="utf-8")
print("V20 eingespielt:", p, "Sicherung:", p.name + ".vor_v20")

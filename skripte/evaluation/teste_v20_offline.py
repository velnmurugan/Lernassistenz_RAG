"""Offline-Test V20 (ohne Ollama): G-v5 unverändert, G-v6 = G-v5 + L8 + L9, Parser und Marker vorhanden."""
import os, sys, importlib.util, hashlib
from pathlib import Path
basis = Path(sys.argv[1] if len(sys.argv) > 1 else "lernassistent")
sys.path.insert(0, str(basis))
def lade(datei, name, g):
    os.environ["LERNASSISTENT_G"] = g
    from importlib.machinery import SourceFileLoader
    lo = SourceFileLoader(name, str(basis / datei)); spec = importlib.util.spec_from_loader(name, lo)
    m = importlib.util.module_from_spec(spec); lo.exec_module(m); return m
ch = [{"id": "x", "thema": "t", "text": "Leistung P = F · v. Beispiel mit anderen Zahlen."}]
q = "Ein Fahrzeug zieht mit 2 kN bei 3 m/s. Welche Leistung ist nötig, und wie groß ist die Arbeit in 10 s?"
ok = 0; n = 0
def check(bed, txt):
    global ok, n; n += 1; ok += bool(bed); print(("OK  " if bed else "FEHLER ") + txt)
neu5 = lade("rag_pipeline.py", "rp_neu5", "G-v5"); alt5 = lade("rag_pipeline.py.vor_v20", "rp_alt5", "G-v5")
check(neu5.baue_scaffolding_prompt(q, ch) == alt5.baue_scaffolding_prompt(q, ch), "G-v5-Prompt unverändert")
neu6 = lade("rag_pipeline.py", "rp_neu6", "G-v6")
p6 = neu6.baue_scaffolding_prompt(q, ch); p5 = neu5.baue_scaffolding_prompt(q, ch)
check(neu6.SCAFFOLDING_VERSION == "G-v6" and neu6.ist_g_version(), "G-v6 aktiv und G-Version")
check("L8 Stehen alle Zahlenwerte" in p6 and "L9 Besteht die Frage" in p6 and "L1 bis L9" in p6, "L8, L9 und Regelnummern im G-v6-Prompt")
zus = p6[p6.index("\nL8 Stehen"):p6.index("\n\nStatus:")]
check(p6.replace(zus, "").replace("L1 bis L9", "L1 bis L7") == p5, "G-v6 = G-v5 + L8/L9 (sonst gleich)")
check("L8" not in p5 and "L9" not in p5, "G-v5 ohne L8/L9")
roh = "STATUS: BEANTWORTET\nLÖSUNG: P = 6 kW; W = 60 kJ.\nÜBERLEGUNG: x\nHINWEIS: Denk an P = F·v."
s = neu6.parse_g_v1(roh); check(s.get("status") == "BEANTWORTET" and "6 kW" in s.get("loesung", ""), "Parser liest G-v6-Antwort")
check(neu6.scaffolding_marker() == alt5.scaffolding_marker(), "Marker wie G-v5")
print(f"\n{ok}/{n} bestanden"); sys.exit(0 if ok == n else 1)

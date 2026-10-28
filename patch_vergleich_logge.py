"""Fügt vergleich_mit_ohne_rag.py die Option --logge hinzu (RAG-Antworten zusätzlich in evaluationsdaten/interaktionen.csv,
damit ragas_auswertung.py sie bewerten kann). Start aus ~/RAG:  python patch_vergleich_logge.py   (idempotent, Sicherung *.vor_logge)"""
import pathlib, shutil, sys
p = pathlib.Path("skripte/evaluation/vergleich_mit_ohne_rag.py")
if not p.exists():
    sys.exit("aus ~/RAG starten")
s = p.read_text(encoding="utf-8")
if "--logge" in s:
    print("schon angepasst"); sys.exit(0)
shutil.copy2(p, p.with_name(p.name + ".vor_logge"))
a1 = '    ap.add_argument("--limit", type=int, default=None)\n'
b1 = a1 + '    ap.add_argument("--logge", action="store_true", help="RAG-Antworten auch in interaktionen.csv protokollieren (für RAGAS)")\n'
a2 = '        z["status_mit"] = erg.get("status", "")\n'
b2 = ('        if args.logge:\n            erg["kb_hash"] = kb_hash\n'
      '            rp.protokolliere_interaktion(args.sitzung, erg, scaffolding_stufe_erreicht=len(rp.scaffolding_marker()))\n') + a2
for a in (a1, a2):
    if s.count(a) != 1:
        sys.exit(f"Anker nicht eindeutig gefunden: {a.strip()}")
s = s.replace(a1, b1, 1).replace(a2, b2, 1)
p.write_text(s, encoding="utf-8")
print("geändert: skripte/evaluation/vergleich_mit_ohne_rag.py (--logge)")

"""vergleich_mit_ohne_rag.py: Zeitüberschreitung (Ollama read timeout) bricht den Lauf nicht mehr ab. Jede Antwort wird bis zu 3-mal
versucht (20 s Pause); danach wird die Frage als FEHLER eingetragen und der Lauf geht weiter.
Start aus ~/RAG:  python patch_vergleich_wiederholung.py   (idempotent, Sicherung *.vor_wiederholung)"""
import pathlib, shutil, sys
p = pathlib.Path("skripte/evaluation/vergleich_mit_ohne_rag.py")
if not p.exists():
    sys.exit("aus ~/RAG starten")
s = p.read_text(encoding="utf-8")
if "_wiederhole(" in s:
    print("schon angepasst"); sys.exit(0)
shutil.copy2(p, p.with_name(p.name + ".vor_wiederholung"))
helper = '''def _wiederhole(fn, ersatz, versuche=3, pause=20):
    """Ruft fn bis zu `versuche`-mal auf (Ollama-Zeitüberschreitung u. ä.); danach `ersatz`, der Lauf geht weiter."""
    for i in range(1, versuche + 1):
        try:
            return fn()
        except Exception as e:
            print(f"   WARNUNG Versuch {i}/{versuche}: {type(e).__name__}: {str(e)[:120]}", flush=True)
            time.sleep(pause)
    return ersatz


def main():'''
ers = [
 ('def main():', helper),
 ('        z["antwort_ohne"] = rp.frage_llm(prompt_ohne_rag(q["frage"]), options=rp.GENERIERUNGS_OPTIONEN)\n',
  '        z["antwort_ohne"] = _wiederhole(lambda: rp.frage_llm(prompt_ohne_rag(q["frage"]), options=rp.GENERIERUNGS_OPTIONEN),\n'
  '                                        "FEHLER (Zeitüberschreitung)")\n'),
 ('        erg = rp.beantworte_frage(q["frage"], chunks, methode=args.retrieval)\n',
  '        erg = _wiederhole(lambda: rp.beantworte_frage(q["frage"], chunks, methode=args.retrieval),\n'
  '                          {"status": "FEHLER", "loesung": "FEHLER (Zeitüberschreitung)", "quellen": []})\n'),
 ('        if args.logge:\n', '        if args.logge and erg.get("status") != "FEHLER":\n'),
]
for a, b in ers:
    if s.count(a) != 1:
        sys.exit(f"Anker nicht eindeutig gefunden: {a.strip()[:50]}")
    s = s.replace(a, b, 1)
p.write_text(s, encoding="utf-8")
print("geändert: skripte/evaluation/vergleich_mit_ohne_rag.py (Wiederholung bei Zeitüberschreitung)")

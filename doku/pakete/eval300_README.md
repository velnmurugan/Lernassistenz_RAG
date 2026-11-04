# Eval300 – 300 questions with and without RAG, judged by a second model

## What it is
- `daten/fragen_eval300.csv` – 300 questions, shuffled with seed 20261101 (ids E001–E300):
  - **N100** (100: Fischer 70 incl. 8 out-of-book, Böge 30)
  - **NEU100** (100: Fischer 45, Böge 45, 10 out-of-book)
  - **V4** (100: Fischer 45, Böge 45, 10 out-of-book A01–A10)
  - Columns: `id, satz, orig_id, buch, typ, frage, referenz, referenz_passage, seite_buch, seite_pdf, kapitel, passage_quelle`.
- `referenz_passage` is the book passage that supports the reference answer:
  - **V4 questions:** the checked quote plus a page excerpt.
  - **N100/NEU100 questions:** a ~1800-character excerpt chosen automatically from the cited PDF page ±3 pages, by word overlap with the reference.
  - The reference answer is authoritative; the passage is an aid. For changed-number calculation questions it shows the formula context, not the numbers.
- The file contains book text: keep it out of Git.
- **Calculation questions (58):** all have complete solutions (Gegeben – Formel – Einsetzen – Ergebnis), recomputed in Python. The 22 N100 short references were expanded; the originals are kept in `referenz_original`. Checking sheet: `Rechenloesungen_pruefen.xlsx`.
- `daten/testfragen_v4.csv` – the 100 v4 questions alone, in the old `testfragen_*.csv` format.

## Run (from ~/RAG, environment pilot_rag, Ollama running)
```bash
cd ~ && python3 -c "import zipfile; zipfile.ZipFile('/mnt/c/Users/Vel Narayanasamy/Downloads/eval300.zip').extractall('.')"
cd ~/RAG && bash ~/eval300/eval300_lauf.sh einrichten    # copies scripts + questions, checks KB hash and models
bash skripte/laeufe/eval300_lauf.sh pilot                 # 6 questions end to end (~10 min)
bash skripte/laeufe/eval300_lauf.sh alles                 # overnight: answers, judge, summary, zip to Downloads
```
- **Configuration:** V11B (frozen), with `LERNASSISTENT_G=G-v4`, `RP-v5`, `FS=aus` and the hint guard off.
- **Generator:** `qwen3.5:9b`, T = 0, seed 42. Without RAG it uses prompt O-v1, the same as the N100/NEU100 runs.
- **Judge:** `qwen3.5:4b` by default (`EVAL300_RICHTER=<tag>` to change). It never uses the generator model.
- **Resuming:** every stage resumes after an interruption (same command).
- **Timing:** about 4–5 h for answers (300 × without + with RAG) and 1–1.5 h for the judge.

## Scripts
| Script | Does |
|---|---|
| `eval300_antworten.py` | Phase 1: answers without and with RAG; stores status, sources and retrieved chunk texts (`kontext_mit`) |
| `eval300_richter.py` | Phase 2: judge prompt R300-v1 with question, reference, book passage, answer (rules below); out-of-book: rule + judge (ABGELEHNT/BEANTWORTET), disagreements flagged |
| `eval300_auswertung.py` | Phase 3: scores (K 1 / T 0.5) per arm, set, book, type; paired sign test; out-of-book refusal rates; **blind rating sheet** `eval300_bewertungsbogen_<LABEL>.xlsx` (no judge verdicts, no set label) |
| `vergleiche_bewertungen.py` | judge vs. Claude vs. Vel: scores per rater, exact agreement, Cohen's kappa (classes and correct yes/no), confusion matrices, CSV of all disagreements |

## Rating rule (same for judge, Claude and Vel; strict N100 rule of 25 Oct 2026)
| Rating | Meaning |
|---|---|
| korrekt | All core statements of the reference, no wrong statement, value, unit or calculation |
| teilweise | Everything stated is right, but part of the core is missing (pure omission) |
| falsch | At least one wrong fact, value, unit or calculation; contradicts the reference; misses the core |
| verweigert | Refuses an in-book question; counts as 0 |
| ablehnung_ok / nicht_abgelehnt | For out-of-book questions only |

## Comparing ratings later
1. Copy `eval300_bewertungsbogen_<LABEL>.xlsx` twice (Vel, Claude) and fill columns I/J independently.
2. Run the comparison:
```bash
python skripte/evaluation/vergleiche_bewertungen.py --richter evaluationsdaten/eval300_richter_EVAL300-V11B_qwen3.5-4b.csv \
   --claude <claude.xlsx> --vel <vel.xlsx>
```

## Limits
- **Judge model:** judge and generator are from the same model family (Qwen 3.5), which may favour the generator's style.
- **Judge validation:** the judge is not validated. Its verdicts are orientation until the hand ratings exist, and kappa against Vel's ratings is the check.
- **Out-of-book refusals:** refusal detection uses the existing rule (`ist_modell_verweigerung`) plus the judge; cases where they disagree are listed for hand checking.
- **Without-RAG prompt:** it says "Fachlehrkraft für Elektrotechnik" for all questions, including Böge and out-of-book ones. It is kept for comparability with N100/NEU100.
- **N100 page numbers:** N100 Böge page numbers come from the old knowledge base. The passage search tolerates ±3 pages; a few passages may still miss.

`herkunft/` contains the scripts that built the set (for documentation; paths refer to the build environment).

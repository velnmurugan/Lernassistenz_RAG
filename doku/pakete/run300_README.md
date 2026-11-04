# run300 – Fragen300 with V20

Answers with and without RAG (qwen3.5:9b, V20), rank of the book page in the search results (Recall@1/@4, MRR),
LLM judge ja / teilweise / nein (gemma4:12b → rating column 3, its reason as a cell comment), Faithfulness with
and without RAG (gemma4:12b), filled rating sheet in Downloads.

```
cd ~ && python3 -c "import zipfile; zipfile.ZipFile('/mnt/c/Users/Vel Narayanasamy/Downloads/run300.zip').extractall('.')"
cd ~/RAG && bash ~/run300/lauf300.sh einrichten    # once: copies scripts/data, checks V20, downloads gemma4:12b (~8 GB)
bash ~/run300/lauf300.sh pilot                       # 3 questions end to end (~10 min) -> Downloads/Fragen300_Bewertung_F300-V20-PILOT.xlsx
bash ~/run300/lauf300.sh teil 100                    # Q1–Q100 only, all steps (~3 h); `alles` later continues with Q101–Q300
bash ~/run300/lauf300.sh zusammen                    # after rating: your ratings + judge/rank/Faithfulness -> Fragen300_komplett_*.xlsx
bash ~/run300/lauf300.sh alles                       # all 300, ~9-10 h
```

Order in `alles`: answers (~4 h) → sheet to Downloads (you can start rating) → rank (~20 min) → judge (~1.5 h)
→ sheet again → Faithfulness (~4 h) → final sheet + raw-data zip. Restart the same command after an interruption.
Single steps: `antworten | rang | richter | faith | bogen`. Other judge: `RUN300_RICHTER=<model>`.

Judge prompt R300-J1: criteria verbatim from the Kriterien tab + 10 examples (removed Eval300 questions, your verdicts),
reason first, then verdict; T = 0, seed 42. Faithfulness: prompts J-v1 from ragas_auswertung.py, both answers against
the same four passages the system retrieved. Rank: a passage counts as the book page if ≥ 40 % of its 4-word
sequences appear on the question's PDF page; 0 = not in the first 50.

Rating copy: right after the answers, `Fragen300_zum_Bewerten_<label>.xlsx` (answers only, blind: no judge verdicts) is written to Downloads once and never overwritten. Rate there; `zusammen` merges columns 1/2 into the run sheet.

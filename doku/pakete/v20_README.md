# V20 – Fragenset V4 nur mit RAG: aktueller Rechenstand vs. + neue Regeln

Two arms on the 18 V4 calculation questions of Eval300, RAG only, T = 0, KB v7r:
- **V19B** = latest calculation stack (RP-v13, RB-v8, V18=ADEK, FS-v3, V19=AB, G-v5, CTX 8192). Never run on V4 before → held-out test of the calc work V13–V19.
- **V20** = V19B + **G-v6** = two new solution rules:
  - L8: if all values are in the question, compute; if the formula is not in the material, use a general basic equation and label it "(Grundgleichung, nicht aus dem Lernmaterial)"; never claim a value is missing that is in the question.
  - L9: multi-part questions: answer every part in order, all requested results in the first sentence.
- Baseline (no new run): EVAL300-V11B, already rated by Vel and Claude.

## Run (from ~/RAG, env pilot_rag, Ollama running)
```
cd ~ && python3 -c "import zipfile; zipfile.ZipFile('/mnt/c/Users/Vel Narayanasamy/Downloads/v20.zip').extractall('.')"
cd ~/RAG && bash ~/v20/v20_lauf.sh einrichten   # patch (backup rag_pipeline.py.vor_v20), offline test 7/7, switch check
bash ~/v20/v20_lauf.sh pilot                     # E047, E084, E055 in both arms (~15 min)
bash ~/v20/v20_lauf.sh lauf                      # 18 calc questions x 2 arms (~1-1.5 h), zip to Downloads
```
G-v1…G-v5 unchanged (tested: G-v5 prompt byte-identical). Undo: `cp lernassistent/rag_pipeline.py.vor_v20 lernassistent/rag_pipeline.py`.

Caveat: L8/L9 were derived from the V4 failures, so V20 on V4 is a development result; V19B on V4 is a clean held-out result.

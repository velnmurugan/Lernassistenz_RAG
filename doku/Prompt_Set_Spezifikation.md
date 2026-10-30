# Prompt Set Specification — Lernassistent (draft v1, 13 Oct 2026)

**Status:** implemented 13 Oct 2026 (V6, see `Entwicklung_und_Evaluation.md` §12 item 2h); first run on both test sets pending, then **freeze**.
**Replaces:** S2-v1 / S2-v2 (generator), H-v3 (separate hint call), IF-v1 (feedback), F-v2 / AR-v3 / CR-v1 (judge).

Source marks: ✓ = in Vel's Notion reading list · NEU = not in the reading list, check before citing.

---

## 1. Why a fixed prompt set

Prompts and judge prompts grew by patching failures observed on one handbook (Böge, *Handbuch Maschinenbau*):

| Patch | Why it does not transfer |
|---|---|
| Judge note "Formeln können verstümmelt sein, D statt =, /SOH statt ·" | Describes extraction artefacts of Springer PDFs; belongs to KB cleaning |
| Few-shot example "Drehstrommotor" in the faithfulness prompt | Domain example; biases the judge on other subjects |
| Refusal detector built from qwen's own phrasing | Breaks with other models or wording (Q28 slipped through in V5) |
| Word lists in Hinweis rules ("Kontext", "Tabelle", …) | Symptom list, not a principle |

Goal: one small set of prompts that (a) works for any vocational text without change, (b) is justified by literature, (c) is frozen and versioned.

## 2. Design principles

| # | Principle | Source |
|---|---|---|
| P1 | **Fixed instructions, variable data.** Domain content enters only through the material and the question. No domain examples, no document-specific rules. | Prompt format sensitivity: Sclar et al. (2024) NEU |
| P2 | **One task per prompt**, chained by the pipeline. | Modular solve / check / feedback: Petukhova, Nguyen & Kochmar (2026) ✓; prompt chaining: Schulhoff et al. (2024) NEU |
| P3 | **Pedagogical rules come from literature**, not from observed failures. | Jangra et al. (2025) ✓; Maurya et al. (2025) ✓; Knievel et al. (2025) ✓; Kochmar et al. (2025) ✓ |
| P4 | **Tutoring outputs are answer-aware**: hint and feedback are written knowing the solution. | Bhaskar & Hamouda (2025) ✓; Petukhova et al. (2026) ✓ |
| P5 | **Hidden reasoning field before the visible tutoring text.** | Zhao, Knežević & Käser (2026) ✓ (46 % → 2 % leakage for Qwen-32B; for Qwen-7B 75 % → 22 %) |
| P6 | **Structured output with an explicit status** instead of inferring refusals from free text. | Abstention when evidence is insufficient: Gala et al. (2026) ✓; tug-of-war: Oche et al. (2025) ✓ |
| P7 | **Judge prompts follow the original RAGAS method**, translated, without tuning to our cases. | Es et al. (2024) ✓ |
| P8 | **Freeze and version.** Change only as a new version with a reason; test on both test sets; acceptance criteria fixed before the run. | Working agreement; held-out testing: Strich et al. (2026) ✓ |

Decisions (Vel, 13 Oct 2026): status field yes · Hinweis and Lösung in **one** call · **no** few-shot examples · robustness test on a second document (Fischer, *Elektrotechnik*, 24 questions).

## 3. Common conventions (all prompts)

1. **Language:** German prompts; learner addressed with „du".
2. **Order:** role and task → rules → material (delimited) → question → output format. The format comes last because small models follow the last instruction most reliably (design choice, not a cited finding).
3. **Delimiting data:** material and question in labelled blocks (`### Lernmaterial`, `### Frage`), so instructions and data are not mixed (Schulhoff et al., 2024 NEU).
4. **Output fields:** uppercase labels at the start of a line followed by a colon (`STATUS:`, `LÖSUNG:` …). Parsing is tolerant to case, bold markers and spaces. Hidden fields are never shown to learners.
5. **No few-shot examples, no domain words, no document-specific notes.**
6. **Generation settings:** temperature 0, seed 42, `think=False` (unchanged). Judge: temperature 0, seed 42.
7. **Fallback:** if a required field is missing, the pipeline uses a fixed fallback (defined per prompt), never the raw model output in a learner-facing field.

## 4. Prompt set

Six prompts: two for tutoring, four for judging.

| ID | Task | Input | Output |
|---|---|---|---|
| **G1** | Antwort: status, solution, hidden plan, hint (one call) | question + 4 chunks | STATUS, LÖSUNG, ÜBERLEGUNG, HINWEIS |
| **G2** | Rückmeldung auf eigene Idee | question + Lösung + Hinweis + idea | ÜBERLEGUNG, URTEIL, RÜCKMELDUNG |
| **J1** | Aussagen zerlegen | question + visible answer | list |
| **J2** | Aussage prüfen | statement + 4 chunks | BEGRÜNDUNG, URTEIL |
| **J3** | Fragen rekonstruieren + ausweichend? | Lösung / question + Lösung | list / BEGRÜNDUNG, AUSWEICHEND |
| **J4** | Benötigte Sätze | question + numbered sentences | BEGRÜNDUNG, BENÖTIGT |

### 4.1 G1 — Antwort (version G-v1)

**Why this order:** the model writes the solution **first** and the hint **last**. The hint is then answer-aware (P4) within one call, and the hidden ÜBERLEGUNG (P5) sits between them. The app still shows the hint first.

**Template:**

```
Du bist ein Lernassistent für Auszubildende. Du beantwortest eine Frage ausschließlich mit dem
Lernmaterial unten und bereitest dazu einen Denkanstoß vor.

Regeln für die Lösung:
L1 Nutze nur Aussagen, die im Lernmaterial stehen oder direkt daraus folgen. Ergänze kein eigenes
   Wissen, auch keine zusätzlichen Begründungen.
L2 Nenne zuerst die Antwort, dann kurz die Begründung aus dem Lernmaterial.
L3 Bei einer Rechnung: Formel, eingesetzte Werte und Ergebnis mit Einheit.
L4 Schreibe verständlich für Auszubildende.

Status:
- BEANTWORTET: Das Lernmaterial beantwortet die Frage.
- TEILWEISE: Das Lernmaterial beantwortet nur einen Teil. Beantworte diesen Teil und nenne, was fehlt.
- NICHT_IM_MATERIAL: Das Lernmaterial beantwortet die Frage nicht. Rate nicht.

Regeln für den Hinweis (die lernende Person sieht nur die Frage, nicht das Lernmaterial und nicht
die Lösung):
H1 Verrate die Lösung nicht, auch nicht mit anderen Worten.
H2 Lenke auf den Begriff, die Größe oder den nächsten Denkschritt, der zur Lösung führt.
H3 Verweise nur auf die Frage und auf Grundwissen, nie auf das Lernmaterial.
H4 Rege zum Nachdenken über einen Zusammenhang an, ohne zu überfordern.
H5 Ein bis zwei kurze Sätze, sprich die lernende Person mit „du" an; du darfst mit einer Frage enden.

### Lernmaterial
{chunks, je Chunk ein Absatz, ohne Kapitelüberschriften}

### Frage
{frage}

Antworte genau in diesem Format:
STATUS: BEANTWORTET oder TEILWEISE oder NICHT_IM_MATERIAL
LÖSUNG: <Lösung nach L1 bis L4; bei NICHT_IM_MATERIAL ein Satz, dass das Lernmaterial dazu nichts enthält>
ÜBERLEGUNG: <nur für dich: welche Kernaussage der Lösung darf der Hinweis nicht verraten, und welcher Denkschritt führt dorthin?>
HINWEIS: <Hinweis nach H1 bis H5; bei NICHT_IM_MATERIAL: –>
```

**Rule sources**

| Rule | Source |
|---|---|
| L1 grounding, no added knowledge | Lewis et al. (2020) ✓; Oche et al. (2025, tug-of-war, §7.1.3) ✓ |
| L2 answer first, then reason | Clarity: Jangra et al. (2025, §2.3, p. 507) ✓ |
| L3 calculations with formula and values | Transparency of the solution path; worked examples: Renkl (2014) NEU; LLM arithmetic is unreliable: Knievel et al. (2025) ✓ |
| L4 level of apprentices | Cognitive load: Sweller (1988) NEU |
| Status values | Gala et al. (2026, abstention) ✓; partial answers instead of refusal: own requirement from the test set definition |
| H1 | Jangra et al. (2025, §4.1, Eq. 1, p. 512) ✓; Maurya et al. (2025, "Revealing Answer") ✓ |
| H2 | Jangra et al. (2025, Scaffolding Support: incremental steps leading to the solution, §2.1, p. 506) ✓; Wood et al. (1976, reduction in degrees of freedom, p. 98) ✓ |
| H3 | Jangra et al. (2025, Link to Prior Knowledge, §2.2, p. 507) ✓; G-v2 wording ("sees only the question") from own app tests (§9a) |
| H4 | Jangra et al. (2025, Conceptual Depth, §2.2, p. 507) ✓; Reiser (2004) ✓ |
| H5 | Jangra et al. (2025, Clarity and Simplicity, §2.3, p. 507) ✓ (the limit of 1–2 sentences is our own setting); guiding question: Neagu et al. (2026) ✓ |
| H6 (G-v2) | own app tests (§9a); no literature source |
| ÜBERLEGUNG | Zhao, Knežević & Käser (2026) ✓ |

*Correction 16 Oct 2026 (Jangra page numbers checked against the printed PDF (TACL 13, pp. 505–528) on 16 Oct 2026): H2 was "convergence, p. 510" and H3 "familiarity, p. 510". Convergence and familiarity are evaluation metrics of Mozafari et al. (2024b), reported by Jangra on p. 511, and do not support these rules; H2 and H3 now cite the matching properties in §2.1/§2.2. H4 page 506 → 507.*

**Parsing and fallback**

| Case | Behaviour |
|---|---|
| STATUS missing or unknown | treat as BEANTWORTET, flag `format_fehler` |
| LÖSUNG missing | whole raw text minus labels as Lösung, no Hinweis, flag `format_fehler` |
| HINWEIS missing or „–" with STATUS ≠ NICHT_IM_MATERIAL | no Hinweis shown (app goes straight to idea box / Lösung), flag |
| STATUS = NICHT_IM_MATERIAL | app shows only the Lösung sentence; no Hinweis, no idea box |

**Effects downstream**
- Refusal detector (regex) is **removed**; evaluation reads STATUS. Correct refusal = NICHT_IM_MATERIAL on an outside question; wrong refusal = NICHT_IM_MATERIAL on an answerable question.
- TEILWEISE answers are scored (faithfulness, AR) like normal answers.
- Interaction log gets one new column `status` (format change → logged with the version).

### 4.2 G2 — Rückmeldung auf die eigene Idee (version IF-v2)

```
Du gibst einer lernenden Person eine kurze Rückmeldung auf ihre eigene Idee zu einer Frage. Du kennst
die richtige Lösung; die lernende Person kennt sie nicht und hat bisher nur die Frage und den Hinweis
gesehen.

Regeln:
F1 Beurteile die Idee anhand der Lösung: RICHTIG, TEILWEISE, FALSCH oder KEINE_IDEE (keine fachliche Idee
   erkennbar).
F2 Benenne, was an der Idee stimmt, und wo genau eine Abweichung liegt.
F3 Gib einen konkreten nächsten Denkschritt, ohne die Lösung zu verraten, auch nicht mit anderen Worten
   und ohne Zahlenwerte aus der Lösung.
F4 Ist die Idee RICHTIG, bestätige sie und sage, dass die Lösung jetzt angezeigt werden kann.
F5 Zwei bis drei kurze Sätze, freundlich und sachlich, sprich die Person mit „du" an.

### Frage
{frage}
### Hinweis (hat die lernende Person gesehen)
{hinweis}
### Lösung (geheim)
{loesung}
### Idee der lernenden Person
{idee}

Antworte genau in diesem Format:
ÜBERLEGUNG: <nur für dich: was stimmt, was fehlt, wie lenke ich, ohne zu verraten?>
URTEIL: RICHTIG oder TEILWEISE oder FALSCH oder KEINE_IDEE
RÜCKMELDUNG: <Rückmeldung nach F2 bis F5>
```

| Rule | Source |
|---|---|
| F1 correctness verdict, answer-aware | Petukhova et al. (2026, gold solution + correctness flag) ✓ |
| F2 identify and locate the mistake | Kochmar et al. (2025, Mistake Identification / Location) ✓; Maurya et al. (2025) ✓ |
| F3 guidance without revealing | Kochmar et al. (2025, Providing Guidance, Actionability) ✓; Wood et al. (1976, marking critical features) ✓ |
| F4 confirmation | Wood et al. (1976, confirmatory role, p. 96) ✓; verification feedback works best: Abrar et al. (2027) ✓ |
| F5 tone, length | Knievel et al. (2025, rules 8–9) ✓; feedback levels: Hattie & Timperley (2007) NEU |
| ÜBERLEGUNG first | Zhao, Knežević & Käser (2026) ✓ |

Change vs. IF-v1: the material chunks are no longer sent (the Lösung is the reference; fewer tokens, no grounding conflict). Number-leak check and max. 3 ideas stay in the code.

### 4.3 J1 — Aussagen zerlegen (faithfulness step 1, version J-v1)

```
Zerlege die Antwort in einzelne Aussagen.

Regeln:
- Jede Aussage enthält genau einen Sachverhalt.
- Jede Aussage ist ohne die anderen verständlich: ersetze Pronomen durch das gemeinte Nomen.
- Lass Aufforderungen an Lernende, Fragen und Aussagen über das Lernmaterial weg.
- Ergänze nichts, was nicht in der Antwort steht.

### Frage
{frage}
### Antwort
{hinweis + lösung}

Gib jede Aussage in einer eigenen Zeile aus, beginnend mit „- ". Sonst nichts.
```

Source: Es et al. (2024, faithfulness: "create one or more statements from each sentence", statements without pronouns) ✓. Removed vs. F-v2: domain example, PDF notes. The meta-statement filter in code stays (counted).

### 4.4 J2 — Aussage prüfen (faithfulness step 2)

```
Prüfe, ob die Aussage durch den Kontext gestützt ist. Nutze ausschließlich den Kontext, nicht dein
eigenes Wissen.

JA: Der Kontext enthält den Sachverhalt, auch mit anderen Worten, oder er folgt direkt daraus.
NEIN: Der Sachverhalt fehlt im Kontext, widerspricht ihm oder geht deutlich über ihn hinaus.

### Kontext
{4 chunks}
### Aussage
{aussage}

Antworte genau in diesem Format:
BEGRÜNDUNG: <ein Satz>
URTEIL: JA oder NEIN
```

Source: Es et al. (2024): "Provide a brief explanation for each statement before arriving at the verdict (Yes/No)" ✓. Documented deviation: one call per statement (robust for small judges). Removed: PDF artefact note (→ KB cleaning, §6).

### 4.5 J3 — Answer relevance

Call a (sees only the Lösung):
```
Formuliere 3 unterschiedliche Fragen, auf die genau diese Antwort passt. Nutze nur, was in der
Antwort steht.

### Antwort
{lösung}

Gib jede Frage in einer eigenen Zeile aus, beginnend mit „- ". Sonst nichts.
```
Call b:
```
Prüfe, ob die Antwort das Gefragte liefert. AUSWEICHEND = JA, wenn sie das Gefragte nicht liefert, z. B.
weil sie allgemein bleibt, obwohl ein bestimmter Wert, eine Liste oder ein Vorgehen gefragt ist.
Ob die Antwort richtig ist, spielt keine Rolle.

### Frage
{frage}
### Antwort
{lösung}

Antworte genau in diesem Format:
BEGRÜNDUNG: <ein Satz>
AUSWEICHEND: JA oder NEIN
```
Source: Es et al. (2024, question generation from the answer only, cosine to the original) ✓; noncommittal check of the reference implementation (Es et al., 2024 / ragas library). Removed vs. AR-v3: "wie Auszubildende sie stellen würden" (domain/audience wording). Answers with STATUS = NICHT_IM_MATERIAL are not scored.

### 4.6 J4 — Context relevance

```
Welche der nummerierten Sätze werden benötigt, um die Frage zu beantworten? Wähle nur Sätze, die direkt
zur Antwort beitragen. Trägt kein Satz dazu bei, antworte mit KEINE. Nutze nur die Sätze, nicht dein
eigenes Wissen.

### Frage
{frage}
### Sätze
[1] …
[2] …

Antworte genau in diesem Format:
BEGRÜNDUNG: <ein Satz>
BENÖTIGT: <Nummern, kommagetrennt> oder KEINE
```
Source: Es et al. (2024, "extract relevant sentences … that can potentially help answer the question") ✓. Documented deviation: selection by number instead of copying sentences (robust for small judges). Removed: PDF note.

## 5. What stays in code (not in prompts)

- Relevance threshold before generation (unchanged).
- Number-leak check for Hinweis and Rückmeldung (`leck_zahlen`), H3 word check in `stufen_check.py` (evaluation only, not a prompt rule).
- Meta-statement filter in J1 parsing (counted).
- Max. 3 ideas per question.

## 6. Moved out of prompts: KB cleaning

PDF artefacts ("D" for "=", "C" for "+", "/SOH", "/NUL", lost symbols) are fixed **when the knowledge base is built**, not explained to the judge. Both Springer PDFs (Böge, Fischer) show the same artefacts. Requires rebuilding the KB, so all versions need a re-run (§7).

## 7. Consequence for comparability

New judge prompts (J-v1) change all scores. Scores are only comparable within the same judge version. Two options:
- **(a)** re-judge V3 and V4 with J-v1 (only the judge runs again, answers stay the same) → clean comparison with the new generator G-v1;
- **(b)** report J-v1 results only from now on and keep the old numbers as history.

Recommendation: (a) for V4 at least, so the effect of G-v1 is measured against the current version under the same judge. Note the run-to-run noise found on 13 Oct: measure it once (V4 repeated) before interpreting small differences.

## 8. Test plan and acceptance criteria (fixed before the run)

Test sets: Böge (`testfragen_v1.csv`, 30) and Fischer (`testfragen_fischer_v1.csv`, 24; second knowledge base, needs `--kb`).

| Criterion | Target | Measured by |
|---|---|---|
| Format complete (all fields) | ≥ 95 % of answers | parser flags |
| STATUS on outside questions = NICHT_IM_MATERIAL | 10/10 (5 + 5) | status vs. test-set type |
| STATUS on answerable questions ≠ NICHT_IM_MATERIAL | ≥ 90 % | status vs. type |
| Hinweis references material (H3 word check) | ≤ 10 % | `stufen_check.py` |
| Hinweis number leak | 0 | `stufen_check.py` |
| Hinweis leak (manual: good / partial / full) | full leak ≤ V4 | manual rating, same categories |
| Faithfulness, clean / critical | not worse than V4 beyond noise | RAGAS J-v1 |
| Böge vs. Fischer | no criterion fails only on Fischer | both runs |

If a criterion fails: document it as a finding; change a prompt only for a reason that is **not specific to one document**, as a new version (G-v2), and re-run both sets.

## 9a. Version log

### G-v2 and IF-v3 (14 Oct 2026; implemented, test run pending)

**Reason (not specific to one document).** Manual tests in the study app (Fischer v7b, session `TEST-V7B`) with questions whose answer is a single value from a table or figure:
- Hints told the learner to look at material they cannot see in 4 of 4 lookup questions: "Schau dir die elektrochemische Spannungsreihe genau an", "Schau dir die im Text genannte Tabelle an", "Schau dir in Abbildung 4.47 … an", "Schau dir das Diagramm an".
- The feedback contradicted a learner who correctly wrote "ich habe keine Tabelle" ("Deine Aussage … ist nicht korrekt, da der Hinweis explizit auf eine … Tabelle verweist") and refused a request for help.
- Earlier feedback cases: one stated the opposite of the solution in one sentence (input power "im Zähler"); one invented a cause for a bare guess ("90 %": "wahrscheinlich … verwechselt").

**Changes to G1 (G-v1 → G-v2):** only the hint rules; solution rules L1–L4, status and output format unchanged.
- H3 new: "Die lernende Person sieht nur die Frage. Sie hat kein Lernmaterial, keine Tabelle, keine Abbildung und keinen Text vor sich. Fordere sie nie auf, etwas anzusehen oder nachzuschlagen."
- H6 new: "Ist die Antwort ein einzelner Wert oder Begriff zum Nachschlagen, lenke auf das Verständnis dahinter: was die Größe bedeutet oder wovon sie abhängt, ohne den Wert zu nennen."

**Changes to G2 (IF-v2 → IF-v3):**
- Introduction: "Sie hat kein Lernmaterial, keine Tabellen und keine Abbildungen. Verweist der Hinweis trotzdem darauf, gehe nicht darauf ein."
- F6: "Sagt die Person, dass sie nicht weiterkommt oder etwas nicht sehen kann, ist das KEINE_IDEE: widersprich ihr nicht, sondern gib einen kleinen zusätzlichen Denkanstoß aus der Frage und dem Grundwissen."
- F7: "Nenne nur Fehlerursachen, die in der Idee erkennbar sind, und prüfe, dass deine Rückmeldung der Lösung nicht widerspricht." [own observation, no literature source]

**Unchanged principles:** no examples, no document-specific wording; G-v1 and IF-v2 stay selectable (`--scaffolding G-v1`, `baue_feedback_prompt(…, version="IF-v2")`) and reproduce V6/V7 exactly (prompt text verified identical).

**Measurement.** The H3 word check is now shared code (`rag_pipeline.MATERIAL_VERWEIS`, used by `stufen_check.py`, `retrieval_erklaeren.py` and logged for feedback) and was extended by Abbildung, Abb., Diagramm, Schaubild, Grafik, nachschlagen, "schau dir … an", Lernmaterial, im Buch. Baseline with the extended check: V4-S2 9/29, V6-BOEGE 6/24, V6-FISCHER 5/22, V7A/V7B2-FISCHER 2/22. Known false positive: "Schau dir an, welche Fläche … den Druck aufnimmt" (V6-BOEGE Q11), i.e. "schau dir an" meaning "consider". The check counts; the final judgement stays manual. The existing test sets contain few lookup questions, so a batch run alone will underestimate the problem; the manual cases are re-tested as well.

**Test plan:** (1) batch run G-v2/IF-v3 on Fischer v7b and Böge, criteria as in §8; (2) re-test the manual cases (zinc −0.76 V, thermal class F 105 K, CdS sensitivity, Abb. 4.47 efficiency, "ich habe keine Tabelle", the three motor-efficiency ideas); (3) adopt as the new fixed version only if no criterion gets worse.

### HP-v1: hint check after generation (14 Oct 2026; implemented, test run pending)

**Reason.** First manual test with G-v2 (session `11`, 11:16–11:19): for "spezifischer Widerstand von Aluminium" the hint still said "… musst du in der Übersicht über die Stoffkonstanten schauen. Welche Spalte enthält dort die Werte für ρ20?". The rule alone does not hold against a context that contains the answer in a table. IF-v3 partly worked (no contradiction of "ich habe keine Tabelle" any more), but the feedback was long and pointed to "Fachliteratur".

**Mechanism (code, `rag_pipeline.hinweis_pruefen`), only for G-v2 and later, only for status BEANTWORTET/TEILWEISE:**
1. The generated hint is checked with `verweist_auf_material` and for numbers from the solution that are not in the question.
2. Clean → shown unchanged (`hinweis_pruefung = ok`).
3. Otherwise one extra call rewrites only the hint (prompt `_prompt_hinweis_neu`: question, secret solution, old hint; same rules as H1–H6 in short form). If the new hint passes the same checks → shown (`nachgebessert`).
4. If it fails again, or the call fails → fixed text: "Für diese Frage habe ich keinen Hinweis, der ohne das Lernmaterial auskommt. Überlege kurz, was du schon über das Thema weißt, und öffne dann die Lösung." (`ersetzt`).
5. `interaktionen.csv` gets two columns, `hinweis_pruefung` and `hinweis_original` (old log rewritten once, with a dated backup). `stufen_check.py` reports the counts; the explainer page shows the result and the original hint.

Cost: one extra model call (about 5–10 s) only when the hint is flagged. G-v1 runs stay unchanged (no check). The check is word-based; false positives (e.g. "schau dir an" meaning "consider") lead to an unnecessary rewrite, not to a wrong answer.

### HP-v2 and IF-v4 (14 Oct 2026; implemented, test run pending)

**Reason.** Test with HP-v1 (session `TEST-V8`):
- Aluminium resistivity: the hint was rewritten into "… typischerweise im Bereich von wenigen Zehntel Ohm pro Meter" (true value 0,02857 Ω·mm²/m: hundredths, other unit). The HP-v1 rewrite prompt allowed "Grundwissen", which the model used as a source of (wrong) facts.
- All three feedbacks then built on this hint ("da der Hinweis … Zehntel andeutet"), one gave the value away as a range ("zwischen 0,02 und 0,03, näher an der unteren Grenze", also wrong in direction), and one pushed the wrong unit of the solution ("Ohm pro Meter").
- Photovoltaics: the feedback called 18–25 % wrong "in der Praxis", because the 2019 textbook gives 10–13 %.
- Positive: the check replaced an unusable hint by the fixed text (thermal class); the concept hint for photovoltaics followed H6; the unit correction for "105 m" (Kelvin, not metres) was very good.

**HP-v2 (code + rewrite prompt):**
- Rewrite prompt: no "Grundwissen"; only concept, meaning of the quantity, what it depends on or the next step; no numbers, ranges, magnitudes or units; no facts that are not in the question or the solution.
- New check `hinweis_hat_wertangabe`: magnitude words (Zehntel, Hundertstel, Tausendstel, Größenordnung, "im Bereich von/zwischen", "zwischen <Zahl>") and digits that are not in the question. Applied to the original and to the rewritten hint; "Prozent" alone does not count.

**IF-v4 (feedback):**
- F6 without "Grundwissen".
- F8: "Maßgeblich ist nur die Lösung. Der Hinweis ist kein Beleg und kann ungenau sein. Formuliere Sachaussagen als Aussage des Lernmaterials („laut Lernmaterial"), nicht als allgemeine Tatsache oder „in der Praxis"."
- F9: "Nenne keine Zahlen, Bereiche oder Größenordnungen, die nicht in der Idee stehen, und sage nicht, ob ein Wert näher an einer Grenze liegt."
- New log columns in `ideen_feedback.csv`: `neue_zahlen` (numbers in the feedback that appear neither in question, hint nor idea) and `verweis_material`; counted by `stufen_check.py`. Old log is rewritten once with a dated backup.

IF-v2 and IF-v3 prompts verified unchanged; HP-v1 behaviour available via `HINWEIS_PRUEFUNG_VERSION = "HP-v1"`.

**Open, not solved by prompts:** (1) the textbook can be outdated (photovoltaics); the system follows the book by design (L1), so a fixed note such as "Werte laut Lehrbuch (Stand 2019)" is a design decision; (2) the unit error "Ω·m" in the solution: cause (extraction of the table header or the model) still to be checked.

### FP-v1, check extensions and freeze for the pilot (14 Oct 2026, "V8d")

**Reason.** Test with HP-v2/IF-v4 (session `TEST-V8C`): hints clean in 2 of 3 cases (photovoltaics, zinc); aluminium still "Überlege, wo du solche tabellarischen Werte … findest" (not caught: "tabellarisch", "wo du … findest"). Feedback: unit errors caught reliably ("0,99 A": current, not voltage; "105 m": Kelvin), "laut Lernmaterial" used, no "in der Praxis" any more; but it still invented a magnitude ("im einstelligen Prozentbereich", wrong: 10–13 %) and gave the solution away ("laut Lernmaterial nur etwa 10–13 %") although F9 forbids it.

**Changes.**
- Material check: `tabellar…`, "wo du/man … find…".
- Value check (used for hints and feedback): einstellig, zweistellig, dreistellig, "untere/obere Grenze".
- **FP-v1** (`ideen_feedback.feedback_pruefen`), same principle as HP-v2: if the feedback contains a number from the solution, a number that appears neither in question, hint nor idea, a magnitude word or a material reference ("laut Lernmaterial" is allowed, F8), one extra call rewrites only the feedback (keeping the verdict); if it fails again, a fixed text per verdict is shown. Verdict RICHTIG is not checked. Log columns `feedback_pruefung`, `rueckmeldung_original`. Known side effect: harmless numbers such as "über 100 %" also trigger a rewrite.

**Freeze.** G-v2 / HP-v2 / IF-v4 / FP-v1 is the candidate version for the pilot. Further changes only after the systematic idea test (below) and a batch run on both books, not after single manual cases.

**Systematic idea test.** `daten/testfragen/testideen_fischer_v1.csv`: 36 learner ideas for 11 questions (Fischer: 4 table lookups, 7 test-set questions), types: correct, unit or sign missing, concrete error (e.g. fraction inverted, √3 missing), vague, meta question ("ich habe keine Tabelle", "positiv oder negativ?"), newer than the book (photovoltaics today), dangerous (current transformer), with the expected verdict. `skripte/evaluation/teste_ideen.py` answers each question once and gives feedback to every idea; output `evaluationsdaten/ideen_test_<SESSION>.csv` with automatic checks (verdict as expected, check outcomes, solution numbers, new numbers) and empty columns for manual rating: correct (ja/nein), leaks (nein/teilweise/ja), helpful (1–3). The same file can be run for every future version.

### G-v3, HP-v3, FP-v2 (14 Oct 2026, "V9")

**Reason.** Idea test `V8D-IDEEN` (36 ideas) and the comparison with vs. without RAG (`RAGVGL-FISCHER`, 33 questions), both pre-rated:
- Q13 (slip): with RAG the solution computed 75/1500 = 0,02 (correct 0,05); without RAG it was correct. The context contained the book example 1440 1/min → 0,04, so the model probably mixed the example into the calculation.
- FP-v1 replaced a very good feedback (I32: "der Faktor √3 fehlt … Wirkungsgrad über 100 %") with the fixed text, because "100" and the "3" of √3 counted as new numbers.
- "schau in deine Unterlagen nach" was not caught by the material check.

**Changes (one rule each, older versions unchanged and selectable):**
- **G-v3** = G-v2 + solution rule **L5**: "Steht im Lernmaterial ein Rechenbeispiel mit anderen Zahlen, übernimm nur den Rechenweg. Rechne mit den Werten aus der Frage und rechne jeden Schritt nach." Hint rules as in G-v2. The solution rules are now kept per version (`_LOESUNGS_REGELN`); G-v1/G-v2 prompts verified byte-identical.
- **HP-v3** = HP-v2 with the extended material check (`MATERIAL_VERWEIS_ERGAENZUNG`: Unterlagen, Aufzeichnungen, Mitschrift, Formelsammlung, Tabellenbuch/Tabellenwerk, Skript, Datenblatt, Notizen). HP-v1/HP-v2 keep the V8d regex.
- **FP-v2** = FP-v1, but "100 %" / "100 Prozent" and numbers directly after √ are ignored in the number checks; extended material check as HP-v3. FP-v1 unchanged.
- Diagnostics (`stufen_check.py`, `retrieval_erklaeren.py`, log column `verweis_material`) always use the extended material check, so their counts for older runs can rise slightly.

**Defaults now:** G-v3 / HP-v3 / IF-v4 / FP-v2. This replaces the V8d freeze as pilot candidate; the same idea test and the with/without-RAG comparison are rerun for V9. Not yet addressed: arithmetic check in code, unit check, figure values, wrong refusals, leaks of the missing step, verdict consistency (see `Entwicklung_und_Evaluation.md` §12, 2n).

### RP-v1 calculation check (14 Oct 2026, "V9d")

**Reason.** Q13 (slip) with RAG: "s = (1500 − 1425) / 1500 = 75 / 1500 = 0,02" (correct 0,05); the correct learner idea "5 %" was then judged wrong. L5 in G-v3 addresses the likely cause (copying numbers from a book example), but a rule cannot guarantee correct arithmetic; written-out calculation steps can be checked deterministically.

**Check (`lernassistent/rechenpruefung.py`, called in `beantworte_frage` before the hint check).** For every equation chain in the solution ("A = B = C", also "≈"): remove units (only known unit symbols directly after a number, unit fractions such as K/W, 1/min, mm²/m), take the computable expression at the edge of each part, evaluate both sides in Python (numbers, + − · /, powers, √, π, %; safe AST evaluation, no `eval`), and compare. Tolerance: half a unit of the last significant digit of the stated number (400 → ±50, 4882 → ±0,5, 0,02 → ±0,005), at least 0.5 %. Deviations by a factor of 10³, 10⁶ … are ignored (silent prefix conversion such as µF → F; unit errors are not this check's job). Parts without numbers ("s", "η", "P₂ / P₁") are skipped.

**Outcomes:** `ok` (no deviation, also when there is no calculation); `nachgebessert` (one extra call gets the first solution and the finding, e.g. "75 / 1500 ergibt 0,05, nicht 0,02", and answers again in the same format; the new solution passes the check; hint and status come from the new answer); `markiert` (the new answer still deviates or fails to parse → the original solution is kept with a visible note "⚠ Automatische Nachrechnung: …"). Logged in `interaktionen.csv` (`rechen_pruefung`, `rechen_befund`, `loesung_original`; old log migrated with a dated backup), in the idea test and in the with/without-RAG comparison (there also as diagnosis for the answer without RAG). Not applied to G-v1/G-v2 (V6–V8 reproducible).

**Offline validation.** 20 constructed cases (correct and wrong steps, units, unit fractions, 1/min, powers of ten, percent, thousands separator "76.200") all as expected. On all 113 real model texts from `V8D-IDEEN` and `RAGVGL-FISCHER` (20 with equations): exactly the Q13 error found (in both runs), no false positives. Limits: only written-out steps; a wrong formula, a bare number without calculation, or LaTeX-formatted answers are not checked.

### G-v4, RP-v2, HP-v4, FP-v3, IF-v5 (19 Oct 2026, "V10"; implemented, runs pending)

**Reason** (runs V9D, 14 Oct 2026, pre-rated; `Entwicklung_und_Evaluation.md` §12, 2o):
- Since G-v3 the model checked its calculation visibly inside the solution: Q13 started with "Der Schlupf beträgt 0,02 oder 2 %" and then corrected itself ("Momentan habe ich einen Rechenfehler … lass uns das korrigieren … 0,05 oder 5 %"); Q27 contained a long deliberation ("*Korrektur basierend auf L1*", "Wiederholtes Überprüfen des Materials"). Most likely cause: "rechne jeden Schritt nach" in L5. RP-v1 reported "ok" for Q13, because every written equation was correct and the wrong 0,02 stood in no equation.
- Hints not caught by HP-v3: "Suche im bereitgestellten Material nach dem Eintrag für Aluminium …", "Wenn du in der elektrochemischen Spannungsreihe nach dem Metall Zink suchst, was siehst du dann …".
- Feedback still named the missing step for TEILWEISE/FALSCH ideas (sign of the zinc potential, "30 °C addieren", "75 durch 1500 teilen", "Reihenschaltung"): 6 of 33 non-safety feedbacks with partial leak in V8D and in V9D.

**Changes (one rule or check each; older versions unchanged and selectable):**
- **G-v4** = G-v3 with L5: "Steht im Lernmaterial ein Rechenbeispiel mit anderen Zahlen, übernimm nur den Rechenweg und rechne mit den Werten aus der Frage." Hint rules as G-v2.
- **RP-v2** = RP-v1 + two deterministic checks (`rechenpruefung.pruefe(text, frage, version)`):
  - *Consistency:* the numbers of the first sentence (L2: answer first) must contain the result of the last real calculation step, i.e. an "=" or "≈" whose left side computes (operator between numbers) and whose right side is a plain number; also accepted as percent (×100, ÷100) and with RP-v1's tolerance and prefix rule (10³, 10⁶). Ignored: numbers from the question, references and standards ("Beispiel 4.15", "Abb. 5.2", "DIN VDE 0100-410"). First sentence = up to the first full stop + space or line break, abbreviations excluded ("ca.", "z. B.", "d. h.", "bzw." …). Skipped if the first sentence has no own number or no calculation follows.
  - *Visible deliberation:* "Rechenfehler", "verrechnet", "momentan habe ich", "ich habe mich geirrt/vertan", first-person correction ("ich/wir korrigiere…", "korrigiere ich/das", "lass uns das korrigieren"), "wiederholtes (Über)prüfen", "prüfen wir", "noch einmal nachrechnen/überprüfen …", "Warte" followed by punctuation, "Korrektur" at the start of a line or after "*"/"(", field names "Entscheidung:", "STATUS:", "ÜBERLEGUNG:". Technical uses ("muss korrigiert werden", "Korrekturfaktor", "Drehmoment") do not count.
  - Rewrite prompt `_prompt_rechnung_neu_v2`: as RP-v1, plus "Die Lösung nennt zuerst das richtige Ergebnis und dann die Begründung, ohne Zwischenüberlegungen und ohne Korrekturen." The new solution must pass all RP-v2 checks.
  - Outcomes: `ok`, `nachgebessert`, `markiert` (note "⚠ Automatische Prüfung: …" only for calculation or consistency findings), **`nicht_behoben`** (only deliberation remains after the rewrite: the original solution is shown without a note, because such a note does not help learners; logged in `rechen_pruefung` / `rechen_befund`).
- **HP-v4** = HP-v3 + `MATERIAL_VERWEIS_V10`: "such… in/im/nach", "nach … such…" (within one sentence; "wonach" does not match), "was siehst du", "bereitgestellt…/vorliegend…/beigefügt…/angehängt… (+ one word) Material/Text/Unterlagen/Informationen/Daten/Dokument".
- **FP-v3** = FP-v2 with the same additional material patterns, so hint and feedback are checked alike.
- **IF-v5** = IF-v4 + **F10**: "Bei TEILWEISE oder FALSCH: Nenne den fehlenden Teil nicht selbst, also keinen fehlenden Rechenschritt, kein fehlendes Vorzeichen und keinen fehlenden Begriff. Frage stattdessen gezielt nach der Stelle, an der er fehlt." [own observation, no literature source]
- `verweist_auf_material(text, erweitert=True, v10=True)`: `v10=False` reproduces HP-v3/FP-v2. Diagnostics (`stufen_check.py`, explainer page, log column `verweis_material`) use the full check, so their counts for older runs can rise slightly.

**Defaults now:** G-v4 / RP-v2 / HP-v4 / IF-v5 / FP-v3 (test version V10; V9D stays selectable).

### RP-v3 (19 Oct 2026, "V10a"; implemented, run pending)
RP-v2 plus one parser fix. Reason: in run V10, Q27 got the false note "4000 / 0,815 ergibt 4908, nicht 1" (the solution said "P1 = 4000 W / 0,815 = 4908 W"; the "1" of the variable name P1 was read as the result).
- Variable names with 1–2 digits (`P1`, `U2`, `R20`) are read as names, not numbers.
- Consequence: an expression that touches a symbol through an operator (`R20 · (1 + 0,004 · 30)`, `0,02 · R20`) is not checked at all (only part of the product would be visible), instead of checking half of it.
- RP-v1 and RP-v2 are unchanged (switch `rag_pipeline.RECHEN_PRUEFUNG_VERSION`); default now RP-v3. G-v4 / HP-v4 / IF-v5 / FP-v3 unchanged.
- Offline test: Q27 gives only the real finding (4908 / (√3 · 400 · 0,85) = 8,334, not 22,9); all earlier RP-v2 cases give the same result under RP-v3; on 111 real solutions RP-v3 flags the same questions as RP-v2.

**Offline validation** (`skripte/evaluation/teste_v10_offline.py`): constructed cases (15 RP-v2, 8 material) and the pipeline flow with a simulated model all pass. Real outputs of V8D/V9D (74 solutions, 106 hints/feedbacks): RP-v2 flags only Q13 and Q27 (V9D) and the known Q13 arithmetic error (V8D); the new material patterns flag only the V9D hints for T1 and T2 and the I08 feedback (true positive). Old prompts verified byte-identical. Limits: RP-v2 sees only written calculations (Q19: a value from a book example without calculation is not caught); the deliberation list is word-based.

## 9. New references (not in the reading list)

- Sclar, M., Choi, Y., Tsvetkov, Y., & Suhr, A. (2024). Quantifying language models' sensitivity to spurious features in prompt design. *ICLR 2024*. [check]
- Schulhoff, S., et al. (2024). The Prompt Report: A systematic survey of prompting techniques. arXiv:2406.06608. [check]
- Renkl, A. (2014). Toward an instructionally oriented theory of example-based learning. *Cognitive Science, 38*(1), 1–37. [check]
- Sweller, J. (1988). Cognitive load during problem solving: Effects on learning. *Cognitive Science, 12*(2), 257–285. [check]
- Hattie, J., & Timperley, H. (2007). The power of feedback. *Review of Educational Research, 77*(1), 81–112. [check]

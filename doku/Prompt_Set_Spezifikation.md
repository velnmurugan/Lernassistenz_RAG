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
| P5 | **Hidden reasoning field before the visible tutoring text.** | Zhao, Knežević & Käser (2026) ✓ (46 % → 2 % leakage) |
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
| H2 | Jangra et al. (2025, convergence, §3.2, p. 510) ✓; Wood et al. (1976, reduction in degrees of freedom, p. 98) ✓ |
| H3 | Jangra et al. (2025, familiarity, p. 510) ✓ |
| H4 | Jangra et al. (2025, conceptual depth, p. 506) ✓; Reiser (2004) ✓ |
| H5 | Jangra et al. (2025, clarity, p. 507) ✓; guiding question: Neagu et al. (2026) ✓ |
| ÜBERLEGUNG | Zhao, Knežević & Käser (2026) ✓ |

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

## 9. New references (not in the reading list)

- Sclar, M., Choi, Y., Tsvetkov, Y., & Suhr, A. (2024). Quantifying language models' sensitivity to spurious features in prompt design. *ICLR 2024*. [check]
- Schulhoff, S., et al. (2024). The Prompt Report: A systematic survey of prompting techniques. arXiv:2406.06608. [check]
- Renkl, A. (2014). Toward an instructionally oriented theory of example-based learning. *Cognitive Science, 38*(1), 1–37. [check]
- Sweller, J. (1988). Cognitive load during problem solving: Effects on learning. *Cognitive Science, 12*(2), 257–285. [check]
- Hattie, J., & Timperley, H. (2007). The power of feedback. *Review of Educational Research, 77*(1), 81–112. [check]

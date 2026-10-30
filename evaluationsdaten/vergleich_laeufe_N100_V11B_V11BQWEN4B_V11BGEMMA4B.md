# N100: Vergleich der Läufe mit Retrieval gegen V11B

Fragen im Referenzlauf: 100. Alle Läufe T = 0, Seed 42; unveränderte Pipeline-Teile liefern identische Antworten.

## Kennzahlen
| Lauf | beantwortet | NICHT_IM_MATERIAL | GATE/andere | Median s (mit) | Median s (ohne) |
|---|---|---|---|---|---|
| V11B | 95 | 5 | 0 | 39 | 4 |
| V11BQWEN4B | 95 | 4 | 1 | 36 | 2 |
| V11BGEMMA4B | 76 | 8 | 16 | 35 | 2 |

## Rechenprüfung (Status, Arm mit Retrieval)
| Lauf | - | ersetzt | markiert | nachgebessert | ok |
|---|---|---|---|---|---|
| V11B | 5 | 3 | 2 | 5 | 85 |
| V11BQWEN4B | 4 | 1 | 4 | 8 | 83 |
| V11BGEMMA4B | 8 | 2 | 1 | 2 | 87 |

## Ablehnungen (NICHT_IM_MATERIAL)
- V11B: 5: F36, F45, F54, F63, F70
- V11BQWEN4B: 4: F36, F45, F54, F63
- V11BGEMMA4B: 8: B27, F36, F40, F45, F54, F55, F63, F70

- Arm ohne Retrieval V11BQWEN4B gegenüber V11B: 0 von 100 Antworten identisch (Kontrolle der Reproduzierbarkeit).
- Arm ohne Retrieval V11BGEMMA4B gegenüber V11B: 0 von 100 Antworten identisch (Kontrolle der Reproduzierbarkeit).

## V11BQWEN4B gegenüber V11B
Identische Antworten (mit Retrieval): 0 von 100; geändert: 100; davon Statuswechsel: 1 (F70).
Handurteil des Referenzlaufs bei den geänderten Fragen: {'-': 100}

| Frage | Typ | Referenz: Urteil | Rechenprüfung ref → neu | Quellen gleich |
|---|---|---|---|---|
| B1 | konzept | - | ok → ok | ja |
| B2 | konzept | - | ok → ok | ja |
| B3 | konzept | - | ok → ok | ja |
| B4 | fakt | - | ok → ok | ja |
| B5 | rechnung | - | ok → ok | ja |
| B6 | konzept | - | ok → ok | ja |
| B7 | tabelle | - | ok → ok | ja |
| B8 | konzept | - | ok → ok | ja |
| B9 | fakt | - | ok → ok | ja |
| B10 | konzept | - | ok → ok | ja |
| B11 | konzept | - | ok → ok | ja |
| B12 | tabelle | - | ok → ok | ja |
| B13 | konzept | - | ok → ok | ja |
| B14 | fakt | - | ok → ok | ja |
| B15 | konzept | - | ok → ok | ja |
| B16 | konzept | - | ok → ok | ja |
| B17 | fakt | - | ok → ok | ja |
| B18 | aufzaehlung | - | ok → ok | ja |
| B19 | konzept | - | ok → ok | ja |
| B20 | konzept | - | ok → ok | ja |
| B21 | konzept | - | ok → ok | ja |
| B22 | konzept | - | ok → ok | ja |
| B23 | konzept | - | ok → ok | ja |
| B24 | rechnung | - | ok → markiert | ja |
| B25 | aufzaehlung | - | ok → ok | ja |
| B26 | fakt | - | ok → ok | ja |
| B27 | rechnung | - | ok → ok | ja |
| B28 | konzept | - | ok → ok | ja |
| B29 | fakt | - | ok → ok | ja |
| B30 | fakt | - | ok → ok | ja |
| F1 | rechnung | - | markiert → ok | ja |
| F2 | rechnung | - | nachgebessert → ok | ja |
| F3 | rechnung | - | ok → ok | ja |
| F4 | rechnung | - | ersetzt → markiert | ja |
| F5 | fakt | - | ok → ok | ja |
| F6 | konzept | - | ok → ok | ja |
| F7 | rechnung | - | nachgebessert → ok | ja |
| F8 | konzept | - | ok → ok | ja |
| F9 | ausserhalb | - | ok → ok | ja |
| F10 | konzept | - | ok → ok | ja |
| F11 | konzept | - | ok → ok | ja |
| F12 | konzept | - | ok → ok | ja |
| F13 | rechnung | - | nachgebessert → nachgebessert | ja |
| F14 | rechnung | - | ok → ok | ja |
| F15 | rechnung | - | ersetzt → ersetzt | ja |
| F16 | konzept | - | ok → ok | ja |
| F17 | konzept | - | ok → ok | ja |
| F18 | ausserhalb | - | ok → ok | ja |
| F19 | konzept | - | ok → ok | ja |
| F20 | fakt | - | ok → ok | ja |
| F21 | konzept | - | ok → ok | ja |
| F22 | konzept | - | ok → ok | ja |
| F23 | konzept | - | ok → ok | ja |
| F24 | konzept | - | ok → ok | ja |
| F25 | konzept | - | ok → ok | ja |
| F26 | konzept | - | ok → ok | ja |
| F27 | ausserhalb | - | ok → ok | ja |
| F28 | konzept | - | ok → ok | ja |
| F29 | rechnung | - | markiert → nachgebessert | ja |
| F30 | konzept | - | ok → ok | ja |
| F31 | konzept | - | ok → ok | ja |
| F32 | fakt | - | ok → ok | ja |
| F33 | konzept | - | ok → ok | ja |
| F34 | konzept | - | ok → ok | ja |
| F35 | fakt | - | ok → ok | ja |
| F36 | ausserhalb | - | - → - | ja |
| F37 | rechnung | - | ok → ok | ja |
| F38 | rechnung | - | ok → ok | ja |
| F39 | rechnung | - | ok → markiert | ja |
| F40 | rechnung | - | nachgebessert → nachgebessert | ja |
| F41 | konzept | - | ok → ok | ja |
| F42 | konzept | - | ok → ok | ja |
| F43 | rechnung | - | ok → nachgebessert | ja |
| F44 | konzept | - | ok → ok | ja |
| F45 | ausserhalb | - | - → - | ja |
| F46 | fakt | - | ok → ok | ja |
| F47 | konzept | - | ok → ok | ja |
| F48 | konzept | - | ok → ok | ja |
| F49 | konzept | - | ok → ok | ja |
| F50 | rechnung | - | ok → nachgebessert | ja |
| F51 | fakt | - | ok → ok | ja |
| F52 | rechnung | - | ok → ok | ja |
| F53 | fakt | - | ok → markiert | ja |
| F54 | ausserhalb | - | - → - | ja |
| F55 | rechnung | - | nachgebessert → nachgebessert | ja |
| F56 | konzept | - | ok → ok | ja |
| F57 | konzept | - | ok → ok | ja |
| F58 | konzept | - | ok → ok | ja |
| F59 | konzept | - | ok → ok | ja |
| F60 | konzept | - | ok → ok | ja |
| F61 | rechnung | - | ersetzt → nachgebessert | ja |
| F62 | rechnung | - | ok → nachgebessert | ja |
| F63 | ausserhalb | - | - → - | ja |
| F64 | konzept | - | ok → ok | ja |
| F65 | konzept | - | ok → ok | ja |
| F66 | konzept | - | ok → ok | ja |
| F67 | fakt | - | ok → ok | ja |
| F68 | konzept | - | ok → ok | ja |
| F69 | konzept | - | ok → ok | ja |
| F70 | ausserhalb | - | - → ok | ja |

Zur Handbewertung: evaluationsdaten/aenderungen_N100_V11BQWEN4B_gegen_V11B.csv

## V11BGEMMA4B gegenüber V11B
Identische Antworten (mit Retrieval): 3 von 100; geändert: 97; davon Statuswechsel: 19 (B5, B7, B13, B18, B19, B24, B27, B30, F4, F7, F9, F13, F18, F29, F37, F40, F52, F55, F61).
Handurteil des Referenzlaufs bei den geänderten Fragen: {'-': 97}

| Frage | Typ | Referenz: Urteil | Rechenprüfung ref → neu | Quellen gleich |
|---|---|---|---|---|
| B1 | konzept | - | ok → ok | ja |
| B2 | konzept | - | ok → ok | ja |
| B3 | konzept | - | ok → ok | ja |
| B4 | fakt | - | ok → ok | ja |
| B5 | rechnung | - | ok → ok | ja |
| B6 | konzept | - | ok → ok | ja |
| B7 | tabelle | - | ok → ok | ja |
| B8 | konzept | - | ok → ok | ja |
| B9 | fakt | - | ok → ok | ja |
| B10 | konzept | - | ok → ok | ja |
| B11 | konzept | - | ok → ok | ja |
| B12 | tabelle | - | ok → ok | ja |
| B13 | konzept | - | ok → ok | ja |
| B14 | fakt | - | ok → ok | ja |
| B15 | konzept | - | ok → ok | ja |
| B16 | konzept | - | ok → ok | ja |
| B17 | fakt | - | ok → ok | ja |
| B18 | aufzaehlung | - | ok → ok | ja |
| B19 | konzept | - | ok → ok | ja |
| B20 | konzept | - | ok → ok | ja |
| B21 | konzept | - | ok → ok | ja |
| B22 | konzept | - | ok → ok | ja |
| B23 | konzept | - | ok → ok | ja |
| B24 | rechnung | - | ok → ok | ja |
| B25 | aufzaehlung | - | ok → ok | ja |
| B26 | fakt | - | ok → ok | ja |
| B27 | rechnung | - | ok → - | ja |
| B28 | konzept | - | ok → ok | ja |
| B29 | fakt | - | ok → ok | ja |
| B30 | fakt | - | ok → ok | ja |
| F1 | rechnung | - | markiert → ok | ja |
| F2 | rechnung | - | nachgebessert → ok | ja |
| F3 | rechnung | - | ok → ok | ja |
| F4 | rechnung | - | ersetzt → ok | ja |
| F5 | fakt | - | ok → ok | ja |
| F6 | konzept | - | ok → ok | ja |
| F7 | rechnung | - | nachgebessert → ok | ja |
| F8 | konzept | - | ok → ok | ja |
| F9 | ausserhalb | - | ok → ok | ja |
| F10 | konzept | - | ok → ok | ja |
| F11 | konzept | - | ok → ok | ja |
| F12 | konzept | - | ok → ok | ja |
| F13 | rechnung | - | nachgebessert → ok | ja |
| F14 | rechnung | - | ok → ersetzt | ja |
| F15 | rechnung | - | ersetzt → nachgebessert | ja |
| F16 | konzept | - | ok → ok | ja |
| F17 | konzept | - | ok → ok | ja |
| F18 | ausserhalb | - | ok → ok | ja |
| F19 | konzept | - | ok → ok | ja |
| F20 | fakt | - | ok → ok | ja |
| F21 | konzept | - | ok → ok | ja |
| F22 | konzept | - | ok → ok | ja |
| F23 | konzept | - | ok → ok | ja |
| F24 | konzept | - | ok → ok | ja |
| F25 | konzept | - | ok → ok | ja |
| F26 | konzept | - | ok → ok | ja |
| F27 | ausserhalb | - | ok → ok | ja |
| F28 | konzept | - | ok → ok | ja |
| F29 | rechnung | - | markiert → ok | ja |
| F30 | konzept | - | ok → ok | ja |
| F31 | konzept | - | ok → ok | ja |
| F33 | konzept | - | ok → ok | ja |
| F34 | konzept | - | ok → ok | ja |
| F35 | fakt | - | ok → ok | ja |
| F37 | rechnung | - | ok → ok | ja |
| F38 | rechnung | - | ok → ok | ja |
| F39 | rechnung | - | ok → markiert | ja |
| F40 | rechnung | - | nachgebessert → - | ja |
| F41 | konzept | - | ok → ok | ja |
| F42 | konzept | - | ok → ok | ja |
| F43 | rechnung | - | ok → ok | ja |
| F44 | konzept | - | ok → ok | ja |
| F45 | ausserhalb | - | - → - | ja |
| F46 | fakt | - | ok → ok | ja |
| F47 | konzept | - | ok → ok | ja |
| F48 | konzept | - | ok → ok | ja |
| F49 | konzept | - | ok → ok | ja |
| F50 | rechnung | - | ok → ok | ja |
| F51 | fakt | - | ok → ok | ja |
| F52 | rechnung | - | ok → ersetzt | ja |
| F53 | fakt | - | ok → ok | ja |
| F54 | ausserhalb | - | - → - | ja |
| F55 | rechnung | - | nachgebessert → - | ja |
| F56 | konzept | - | ok → ok | ja |
| F57 | konzept | - | ok → ok | ja |
| F58 | konzept | - | ok → ok | ja |
| F59 | konzept | - | ok → ok | ja |
| F60 | konzept | - | ok → ok | ja |
| F61 | rechnung | - | ersetzt → ok | ja |
| F62 | rechnung | - | ok → nachgebessert | ja |
| F63 | ausserhalb | - | - → - | ja |
| F64 | konzept | - | ok → ok | ja |
| F65 | konzept | - | ok → ok | ja |
| F66 | konzept | - | ok → ok | ja |
| F67 | fakt | - | ok → ok | ja |
| F68 | konzept | - | ok → ok | ja |
| F69 | konzept | - | ok → ok | ja |

Zur Handbewertung: evaluationsdaten/aenderungen_N100_V11BGEMMA4B_gegen_V11B.csv

## V11BQWEN4B gegen V11BGEMMA4B: 99 Fragen mit unterschiedlicher Antwort: B1, B10, B11, B12, B13, B14, B15, B16, B17, B18, B19, B2, B20, B21, B22, B23, B24, B25, B26, B27, B28, B29, B3, B30, B4, B5, B6, B7, B8, B9, F1, F10, F11, F12, F13, F14, F15, F16, F17, F18, F19, F2, F20, F21, F22, F23, F24, F25, F26, F27, F28, F29, F3, F30, F31, F32, F33, F34, F35, F36, F37, F38, F39, F4, F40, F41, F42, F43, F44, F45, F46, F47, F48, F49, F5, F50, F51, F52, F53, F54, F55, F56, F57, F58, F59, F6, F61, F62, F63, F64, F65, F66, F67, F68, F69, F7, F70, F8, F9

Hinweis: Skript wertet nur Gleichheit und Status; ob eine geänderte Antwort besser oder schlechter ist, entscheidet die Handbewertung (hand_neu).

# N100: Vergleich der Läufe mit Retrieval gegen V11B

Fragen im Referenzlauf: 100. Alle Läufe T = 0, Seed 42; unveränderte Pipeline-Teile liefern identische Antworten.

## Kennzahlen
| Lauf | beantwortet | NICHT_IM_MATERIAL | GATE/andere | Median s (mit) | Median s (ohne) |
|---|---|---|---|---|---|
| V11B | 95 | 5 | 0 | 39 | 4 |
| V19AUS | 94 | 5 | 1 | 38 | 4 |
| V19AB | 95 | 5 | 0 | 39 | 4 |

## Rechenprüfung (Status, Arm mit Retrieval)
| Lauf | - | denkmodus | ersetzt | kopf_korrigiert | markiert | nachgebessert | ok | ungeprueft |
|---|---|---|---|---|---|---|---|---|
| V11B | 5 | 0 | 3 | 0 | 2 | 5 | 85 | 0 |
| V19AUS | 5 | 0 | 7 | 1 | 1 | 5 | 78 | 3 |
| V19AB | 5 | 1 | 5 | 0 | 2 | 5 | 78 | 4 |

## Ablehnungen (NICHT_IM_MATERIAL)
- V11B: 5: F36, F45, F54, F63, F70
- V19AUS: 5: F36, F45, F54, F63, F70
- V19AB: 5: F36, F45, F54, F63, F70

- Arm ohne Retrieval V19AUS gegenüber V11B: 100 von 100 Antworten identisch (Kontrolle der Reproduzierbarkeit).
- Arm ohne Retrieval V19AB gegenüber V11B: 100 von 100 Antworten identisch (Kontrolle der Reproduzierbarkeit).

## V19AUS gegenüber V11B
Identische Antworten (mit Retrieval): 25 von 100; geändert: 75; davon Statuswechsel: 1 (F39).
Handurteil des Referenzlaufs bei den geänderten Fragen: {'-': 75}

| Frage | Typ | Referenz: Urteil | Rechenprüfung ref → neu | Quellen gleich |
|---|---|---|---|---|
| B1 | konzept | - | ok → ok | ja |
| B2 | konzept | - | ok → ok | ja |
| B3 | konzept | - | ok → ok | ja |
| B5 | rechnung | - | ok → ok | ja |
| B6 | konzept | - | ok → ok | ja |
| B7 | tabelle | - | ok → ok | ja |
| B8 | konzept | - | ok → ok | ja |
| B11 | konzept | - | ok → ok | ja |
| B12 | tabelle | - | ok → ok | ja |
| B13 | konzept | - | ok → ok | ja |
| B14 | fakt | - | ok → ok | ja |
| B19 | konzept | - | ok → ok | ja |
| B20 | konzept | - | ok → ok | ja |
| B21 | konzept | - | ok → ok | ja |
| B22 | konzept | - | ok → ok | ja |
| B23 | konzept | - | ok → ok | ja |
| B24 | rechnung | - | ok → ersetzt | ja |
| B25 | aufzaehlung | - | ok → ok | ja |
| B26 | fakt | - | ok → ok | ja |
| B27 | rechnung | - | ok → ersetzt | ja |
| B28 | konzept | - | ok → ok | ja |
| B30 | fakt | - | ok → ungeprueft | ja |
| F1 | rechnung | - | markiert → ersetzt | ja |
| F2 | rechnung | - | nachgebessert → ok | ja |
| F3 | rechnung | - | ok → ok | ja |
| F4 | rechnung | - | ersetzt → kopf_korrigiert | ja |
| F5 | fakt | - | ok → ok | ja |
| F6 | konzept | - | ok → ok | ja |
| F7 | rechnung | - | nachgebessert → nachgebessert | ja |
| F9 | ausserhalb | - | ok → ok | ja |
| F11 | konzept | - | ok → ok | ja |
| F12 | konzept | - | ok → ok | ja |
| F14 | rechnung | - | ok → ok | ja |
| F15 | rechnung | - | ersetzt → ersetzt | ja |
| F16 | konzept | - | ok → ok | ja |
| F17 | konzept | - | ok → ok | ja |
| F18 | ausserhalb | - | ok → ok | ja |
| F19 | konzept | - | ok → ok | ja |
| F21 | konzept | - | ok → ok | ja |
| F22 | konzept | - | ok → ok | ja |
| F23 | konzept | - | ok → ok | ja |
| F24 | konzept | - | ok → ok | ja |
| F25 | konzept | - | ok → ok | ja |
| F26 | konzept | - | ok → ok | ja |
| F28 | konzept | - | ok → ok | ja |
| F29 | rechnung | - | markiert → ersetzt | ja |
| F30 | konzept | - | ok → ungeprueft | ja |
| F31 | konzept | - | ok → ok | ja |
| F33 | konzept | - | ok → ok | ja |
| F36 | ausserhalb | - | - → - | ja |
| F39 | rechnung | - | ok → markiert | ja |
| F40 | rechnung | - | nachgebessert → nachgebessert | ja |
| F41 | konzept | - | ok → ok | ja |
| F42 | konzept | - | ok → ok | ja |
| F44 | konzept | - | ok → ok | ja |
| F45 | ausserhalb | - | - → - | ja |
| F46 | fakt | - | ok → ok | ja |
| F48 | konzept | - | ok → ok | ja |
| F49 | konzept | - | ok → ok | ja |
| F50 | rechnung | - | ok → ok | ja |
| F51 | fakt | - | ok → ok | ja |
| F52 | rechnung | - | ok → nachgebessert | ja |
| F53 | fakt | - | ok → ok | ja |
| F55 | rechnung | - | nachgebessert → nachgebessert | ja |
| F56 | konzept | - | ok → ok | ja |
| F58 | konzept | - | ok → ok | ja |
| F60 | konzept | - | ok → ok | ja |
| F61 | rechnung | - | ersetzt → ersetzt | ja |
| F62 | rechnung | - | ok → ersetzt | ja |
| F63 | ausserhalb | - | - → - | ja |
| F64 | konzept | - | ok → ok | ja |
| F65 | konzept | - | ok → ok | ja |
| F66 | konzept | - | ok → ok | ja |
| F69 | konzept | - | ok → ok | ja |
| F70 | ausserhalb | - | - → - | ja |

Zur Handbewertung: evaluationsdaten/aenderungen_N100_V19AUS_gegen_V11B.csv

## V19AB gegenüber V11B
Identische Antworten (mit Retrieval): 22 von 100; geändert: 78; davon Statuswechsel: 0 (-).
Handurteil des Referenzlaufs bei den geänderten Fragen: {'-': 78}

| Frage | Typ | Referenz: Urteil | Rechenprüfung ref → neu | Quellen gleich |
|---|---|---|---|---|
| B1 | konzept | - | ok → ok | ja |
| B2 | konzept | - | ok → ok | ja |
| B3 | konzept | - | ok → ok | ja |
| B5 | rechnung | - | ok → ok | ja |
| B6 | konzept | - | ok → ok | ja |
| B7 | tabelle | - | ok → ok | ja |
| B8 | konzept | - | ok → ok | ja |
| B11 | konzept | - | ok → ok | ja |
| B12 | tabelle | - | ok → ok | ja |
| B13 | konzept | - | ok → ok | ja |
| B14 | fakt | - | ok → ok | ja |
| B19 | konzept | - | ok → ok | ja |
| B20 | konzept | - | ok → ok | ja |
| B21 | konzept | - | ok → ok | ja |
| B22 | konzept | - | ok → ok | ja |
| B23 | konzept | - | ok → ok | ja |
| B24 | rechnung | - | ok → ersetzt | ja |
| B25 | aufzaehlung | - | ok → ok | ja |
| B26 | fakt | - | ok → ok | ja |
| B27 | rechnung | - | ok → ungeprueft | nein |
| B28 | konzept | - | ok → ok | ja |
| B30 | fakt | - | ok → ungeprueft | nein |
| F1 | rechnung | - | markiert → ok | nein |
| F2 | rechnung | - | nachgebessert → ok | nein |
| F3 | rechnung | - | ok → ok | nein |
| F4 | rechnung | - | ersetzt → markiert | nein |
| F5 | fakt | - | ok → ok | ja |
| F6 | konzept | - | ok → ok | ja |
| F7 | rechnung | - | nachgebessert → nachgebessert | nein |
| F9 | ausserhalb | - | ok → ok | ja |
| F11 | konzept | - | ok → ok | ja |
| F12 | konzept | - | ok → ok | ja |
| F13 | rechnung | - | nachgebessert → ersetzt | nein |
| F14 | rechnung | - | ok → ok | nein |
| F15 | rechnung | - | ersetzt → denkmodus | nein |
| F16 | konzept | - | ok → ok | ja |
| F17 | konzept | - | ok → ok | ja |
| F18 | ausserhalb | - | ok → ok | ja |
| F19 | konzept | - | ok → ok | ja |
| F21 | konzept | - | ok → ok | ja |
| F22 | konzept | - | ok → ok | ja |
| F23 | konzept | - | ok → ok | ja |
| F24 | konzept | - | ok → ok | ja |
| F25 | konzept | - | ok → ok | ja |
| F26 | konzept | - | ok → ok | ja |
| F28 | konzept | - | ok → ok | ja |
| F29 | rechnung | - | markiert → nachgebessert | nein |
| F30 | konzept | - | ok → ungeprueft | nein |
| F31 | konzept | - | ok → ok | ja |
| F33 | konzept | - | ok → ok | ja |
| F36 | ausserhalb | - | - → - | ja |
| F37 | rechnung | - | ok → ungeprueft | nein |
| F39 | rechnung | - | ok → markiert | nein |
| F40 | rechnung | - | nachgebessert → ersetzt | nein |
| F41 | konzept | - | ok → ok | ja |
| F42 | konzept | - | ok → ok | ja |
| F43 | rechnung | - | ok → nachgebessert | nein |
| F44 | konzept | - | ok → ok | ja |
| F45 | ausserhalb | - | - → - | ja |
| F46 | fakt | - | ok → ok | ja |
| F48 | konzept | - | ok → ok | ja |
| F49 | konzept | - | ok → ok | ja |
| F50 | rechnung | - | ok → ok | ja |
| F51 | fakt | - | ok → ok | ja |
| F52 | rechnung | - | ok → nachgebessert | nein |
| F53 | fakt | - | ok → ok | ja |
| F55 | rechnung | - | nachgebessert → nachgebessert | nein |
| F56 | konzept | - | ok → ok | ja |
| F58 | konzept | - | ok → ok | ja |
| F60 | konzept | - | ok → ok | ja |
| F61 | rechnung | - | ersetzt → ersetzt | nein |
| F62 | rechnung | - | ok → ersetzt | nein |
| F63 | ausserhalb | - | - → - | ja |
| F64 | konzept | - | ok → ok | ja |
| F65 | konzept | - | ok → ok | ja |
| F66 | konzept | - | ok → ok | ja |
| F69 | konzept | - | ok → ok | ja |
| F70 | ausserhalb | - | - → - | ja |

Zur Handbewertung: evaluationsdaten/aenderungen_N100_V19AB_gegen_V11B.csv

## V19AUS gegen V19AB: 19 Fragen mit unterschiedlicher Antwort: B27, B30, F1, F13, F14, F15, F2, F29, F3, F30, F37, F39, F4, F40, F43, F52, F55, F62, F7

Hinweis: Skript wertet nur Gleichheit und Status; ob eine geänderte Antwort besser oder schlechter ist, entscheidet die Handbewertung (hand_neu).

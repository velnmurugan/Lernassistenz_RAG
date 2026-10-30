# N100: Modellvergleich bei gleicher Pipeline-Konfiguration (V11B)

Nur das Generator-Modell wechselt (T = 0, Seed 42). Referenz: V11B (qwen3.5:9b). Kennzahlen sind formal (Status, Format, Zeit); die Richtigkeit wird per Handbewertung festgelegt.

## Mit Retrieval
| Lauf | Fragen | beantwortet | Ablehnung | zu Recht abgelehnt (außerhalb) | zu Unrecht abgelehnt | FEHLER | Denkreste | deutsch | Median Zeichen | Median s | Gesamt h |
|---|---|---|---|---|---|---|---|---|---|---|---|
| V11B | 100 | 95 | 5 | 5/8 | 0/92 | 0 | 1 | 100 | 285 | 39 | 6.48 |
| V11BQWEN4B | 100 | 95 | 4 | 4/8 | 0/92 | 0 | 0 | 100 | 228 | 36 | 1.06 |
| V11BGEMMA4B | 100 | 76 | 8 | 5/8 | 3/92 | 0 | 0 | 100 | 218 | 35 | 1.00 |

## Ohne Retrieval
| Lauf | FEHLER | Denkreste | deutsch | Median Zeichen | Median s | Gesamt h |
|---|---|---|---|---|---|---|
| V11B | 0 | 0 | 100 | 640 | 4 | 0.15 |
| V11BQWEN4B | 0 | 0 | 100 | 582 | 2 | 0.06 |
| V11BGEMMA4B | 0 | 0 | 100 | 571 | 2 | 0.06 |

## Rechenprüfung (RP-v5, Arm mit Retrieval)
| Lauf | - | ersetzt | markiert | nachgebessert | ok |
|---|---|---|---|---|---|
| V11B | 5 | 3 | 2 | 5 | 85 |
| V11BQWEN4B | 4 | 1 | 4 | 8 | 83 |
| V11BGEMMA4B | 8 | 2 | 1 | 2 | 87 |

## Übereinstimmung mit der Referenz (Status)
- V11BQWEN4B: gleicher Status wie V11B bei 99 von 100 Fragen.
- V11BGEMMA4B: gleicher Status wie V11B bei 81 von 100 Fragen.

Hinweis: Entwicklungs- und Pilotfragen; keine Evidenz für den Beitrag ohne unabhängigen Satz.

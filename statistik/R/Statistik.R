# =====================================================================
# Kennwerte für Tabellen 2–4 und den Ergebnistext (Abschnitt 5.2).
# Läuft im jamovi-Modul "Rj Editor" (`data` = geöffnete Tabelle) und in R.
# Nur Basis-R; keine Zusatzpakete nötig.
# =====================================================================
if (!is.data.frame(data)) data <- readxl::read_excel("Daten_Beitrag_jamovi.xlsx", sheet = "Daten")
# Zahlenspalten sicher lesen: jamovi legt Spalten mit wenigen ganzen Zahlen (z. B. Rang_Buchstelle) als
# nominal an; as.numeric() würde dann die Stufennummer statt des Werts liefern.
zahl <- function(x) as.numeric(as.character(x))
options(width = 200)
d   <- as.data.frame(data)
buch <- d[as.character(d$Typ) != "Außerhalb", ]
auss <- d[as.character(d$Typ) == "Außerhalb", ]

bed  <- c(qwen_ohne = "A qwen ohne RAG", qwen_mit = "B qwen mit RAG",
          GPT_ohne  = "C GPT ohne RAG",  GPT_mit  = "D GPT mit RAG")
bew  <- c(Mensch = "Menschliche Bewertung", Gemini = "Gemini", Mistral = "Mistral")
pkt  <- function(x) c(ja = 1, teilweise = 0.5, nein = 0)[as.character(x)]
fmt  <- function(x, n = 1) formatC(floor(x * 10^n + 0.5 + 1e-9) / 10^n, format = "f", digits = n, decimal.mark = ",")  # kaufmännisch runden wie Excel
proz <- function(x, n = 1) paste0(fmt(100 * x, n), " %")
wilson <- function(k, n) { ci <- prop.test(k, n, correct = FALSE)$conf.int; paste0(fmt(100 * ci[1]), "–", fmt(100 * ci[2])) }
vorzeichen <- function(a, b) {             # Vorzeichentest über Fragen mit unterschiedlichem Wert
  diff <- a - b; diff <- diff[!is.na(diff) & diff != 0]
  c(besser = sum(diff > 0), schlechter = sum(diff < 0),
    p = if (length(diff)) binom.test(sum(diff > 0), length(diff))$p.value else NA)
}
kappa <- function(a, b) {                  # Cohens Kappa (ungewichtet)
  ok <- !is.na(a) & !is.na(b); a <- as.character(a[ok]); b <- as.character(b[ok])
  st <- union(a, b); t <- table(factor(a, st), factor(b, st)) / length(a)
  po <- sum(diag(t)); pe <- sum(rowSums(t) * colSums(t))
  c(uebereinstimmung = po, kappa = (po - pe) / (1 - pe))
}
p_text <- function(p) ifelse(p < 0.001, "< 0,001", fmt(p, 2))

cat("=== Tabelle 2: Antwortqualität je Bedingung (", nrow(buch), "Buchfragen ) ===\n")
t2 <- do.call(rbind, lapply(names(bed), function(b) {
  x <- as.character(buch[[paste0(b, "_Mensch")]]); n <- sum(!is.na(x))
  k <- sum(x == "ja"); tw <- sum(x == "teilweise"); f <- sum(x == "nein")
  out <- as.character(auss[[paste0(b, "_Mensch")]])
  data.frame(Bedingung = bed[b], "korrekt/teilweise/falsch" = paste(k, tw, f, sep = " / "),
             "Anteil korrekt" = proz(k / n), "95-%-KI" = wilson(k, n),
             Punktanteil = proz(mean(pkt(x), na.rm = TRUE)),
             "Außerhalb abgewiesen" = paste0(sum(out == "ja"), " / ", length(out)),
             check.names = FALSE, row.names = NULL)
}))
print(t2, row.names = FALSE)

cat("\n=== Punktanteil je Bewertung ===\n")
print(sapply(names(bew), function(r) sapply(names(bed), function(b)
  proz(mean(pkt(buch[[paste0(b, "_", r)]]), na.rm = TRUE)))), quote = FALSE)

cat("\n=== Paarvergleiche (Vorzeichentest) je Bewertung ===\n")
vgl <- list(c("qwen_mit", "qwen_ohne"), c("GPT_mit", "GPT_ohne"), c("qwen_mit", "GPT_ohne"), c("GPT_mit", "qwen_mit"))
for (r in names(bew)) for (v in vgl) {
  z <- vorzeichen(pkt(buch[[paste0(v[1], "_", r)]]), pkt(buch[[paste0(v[2], "_", r)]]))
  dpp <- 100 * (mean(pkt(buch[[paste0(v[1], "_", r)]]), na.rm = TRUE) - mean(pkt(buch[[paste0(v[2], "_", r)]]), na.rm = TRUE))
  cat(sprintf("%-22s %-10s vs. %-10s besser %3d  schlechter %3d  p %s  Differenz %s Prozentpunkte\n",
              bew[r], v[1], v[2], z["besser"], z["schlechter"], p_text(z["p"]), fmt(dpp)))
}

cat("\n=== Punktanteil nach Fragetyp (menschliche Bewertung) ===\n")
typen <- c("Konzept", "Fakt", "Rechnung", "Tabellenabfrage", "Aufzählung")
print(sapply(names(bed), function(b) sapply(typen, function(t)
  proz(mean(pkt(buch[as.character(buch$Typ) == t, paste0(b, "_Mensch")]), na.rm = TRUE)))), quote = FALSE)

cat("\n=== Übereinstimmung der Bewertungen (alle", 4 * nrow(d), "Antworten) ===\n")
alle <- function(r) unlist(lapply(names(bed), function(b) as.character(d[[paste0(b, "_", r)]])))
for (pr in list(c("Mensch", "Gemini"), c("Mensch", "Mistral"), c("Gemini", "Mistral"))) {
  k <- kappa(alle(pr[1]), alle(pr[2]))
  cat(sprintf("%-8s – %-8s Übereinstimmung %s  kappa %s\n", pr[1], pr[2], proz(k[1]), fmt(k[2], 2)))
}
kj <- unlist(lapply(names(bed), function(b) lapply(list(c("Mensch", "Gemini"), c("Mensch", "Mistral"), c("Gemini", "Mistral")),
      function(pr) kappa(d[[paste0(b, "_", pr[1])]], d[[paste0(b, "_", pr[2])]])["kappa"])))
cat(sprintf("kappa je Bedingung und Paar: %s bis %s\n", fmt(min(kj), 2), fmt(max(kj), 2)))

cat("\n=== Tabelle 3: Retrieval, Faithfulness, Antwortzeit ===\n")
rang <- zahl(buch$Rang_Buchstelle)
cat(sprintf("Recall@1 %s  Recall@4 %s  MRR %s  (gefunden bis Platz 4: %d von %d)\n",
            proz(mean(rang == 1)), proz(mean(rang >= 1 & rang <= 4)), fmt(mean(ifelse(rang > 0, 1 / rang, 0)), 2),
            sum(rang >= 1 & rang <= 4), length(rang)))
rech <- as.character(buch$Typ) == "Rechnung"
for (b in names(bed)) {
  f <- zahl(buch[[paste0("Faith_", b)]]); z <- zahl(d[[paste0("Zeit_", b)]])
  cat(sprintf("%-16s Faithfulness alle %s  ohne Rechenfragen %s (n = %d)  Zeit Median %s s (Mittel %s s)\n",
              bed[b], fmt(mean(f, na.rm = TRUE), 2), fmt(mean(f[!rech], na.rm = TRUE), 2), sum(!rech), fmt(median(z, na.rm = TRUE)), fmt(mean(z, na.rm = TRUE))))
}
for (v in list(c("qwen_mit", "qwen_ohne"), c("GPT_mit", "GPT_ohne"), c("GPT_mit", "qwen_mit"))) {
  z <- vorzeichen(zahl(buch[[paste0("Faith_", v[1])]]), zahl(buch[[paste0("Faith_", v[2])]]))
  cat(sprintf("Faithfulness %s vs. %s: höher %d, niedriger %d, p %s\n", v[1], v[2], z["besser"], z["schlechter"], p_text(z["p"])))
}
gef <- rang >= 1 & rang <= 4
for (b in c("qwen_mit", "GPT_mit")) {
  s <- pkt(buch[[paste0(b, "_Mensch")]])
  cat(sprintf("%s: Punktanteil Buchstelle gefunden %s (n = %d), nicht gefunden %s (n = %d)\n",
              b, proz(mean(s[gef])), sum(gef), proz(mean(s[!gef])), sum(!gef)))
}

cat("\n=== Tabelle 4: Bewertung der Hinweise ===\n")
h <- d[!is.na(d$H1_korrekt) & as.character(d$H1_korrekt) != "", ]; n <- nrow(h)
ja <- function(x) as.character(x) == "ja"
akz <- ja(h$H1_korrekt) & ja(h$H2_offen) & ja(h$H4_verstaendlich) & as.character(h$H3_schritt) %in% c("ja", "teilweise")
stk <- akz & ja(h$H3_schritt)
cat(sprintf("Akzeptabel %d  %s (%s)\ndavon stark %d  %s (%s)\n", sum(akz), proz(sum(akz) / n), wilson(sum(akz), n),
            sum(stk), proz(sum(stk) / n), wilson(sum(stk), n)))
for (k in c("H1_korrekt", "H2_offen", "H3_schritt", "H4_verstaendlich")) {
  t <- table(as.character(h[[k]]))
  cat(sprintf("%-17s %s\n", k, paste(sprintf("%s %d (%s)", names(t), t, proz(t / n)), collapse = "  ")))
}

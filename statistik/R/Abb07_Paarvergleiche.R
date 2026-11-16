# =====================================================================
# Abbildung 7 – Paarvergleiche je Frage (270 Buchfragen, menschliche
# Bewertung): Anteil der Fragen, bei denen die erste Bedingung besser,
# gleich oder schlechter bewertet wurde als die zweite.
# Läuft im jamovi-Modul "Rj Editor" (`data` = geöffnete Tabelle) und in R.
# =====================================================================
if (!is.data.frame(data)) data <- readxl::read_excel("Daten_Beitrag_jamovi.xlsx", sheet = "Daten")
library(ggplot2)
speichern <- FALSE
breite_cm <- 18; hoehe_cm <- 8   # Größe der Abbildung im Beitrag
# Die Abbildung wird immer in Originalgröße gezeichnet. In jamovi (Rj Editor) dafür im Zahnrad-Menü
# "Figure size (px)" Width = 512 und Height = 314 eintragen (1 px = 1/72 Zoll; 18 × 11 cm).
skal <- 1   # Verkleinerungsfaktor für Schrift und Linien (1 = wie im Beitrag)
bewertung <- "Mensch"          # "Mensch", "Gemini" oder "Mistral"

d <- as.data.frame(data)
d <- d[as.character(d$Typ) != "Außerhalb", ]
punkte <- function(x) c(ja = 1, teilweise = 0.5, nein = 0)[as.character(x)]
s <- function(b) punkte(d[[paste0(b, "_", bewertung)]])

vergleiche <- list(                     # erste Bedingung, zweite Bedingung, Beschriftung
  c("qwen_mit", "qwen_ohne", "qwen: mit vs. ohne RAG"),
  c("GPT_mit",  "GPT_ohne",  "GPT: mit vs. ohne RAG"),
  c("qwen_mit", "GPT_ohne",  "qwen mit RAG vs. GPT ohne RAG"),
  c("GPT_mit",  "qwen_mit",  "GPT mit RAG vs. qwen mit RAG"))

tab <- do.call(rbind, lapply(vergleiche, function(v) {
  diff <- s(v[1]) - s(v[2])
  n <- c(schlechter = sum(diff < 0, na.rm = TRUE), gleich = sum(diff == 0, na.rm = TRUE),
         besser = sum(diff > 0, na.rm = TRUE))
  data.frame(Vergleich = v[3], Ergebnis = names(n), n = as.numeric(n), Anteil = as.numeric(n) / sum(n))
}))
tab$Vergleich <- factor(tab$Vergleich, levels = rev(sapply(vergleiche, `[`, 3)))
tab$Ergebnis  <- factor(tab$Ergebnis, levels = c("besser", "gleich", "schlechter"))  # schlechter links
tab$Label     <- ifelse(tab$n >= 15, tab$n, "")
tab$Textfarbe <- ifelse(tab$Ergebnis == "gleich", "black", "white")

farben  <- c(schlechter = "#D73027", gleich = "#CCCCCC", besser = "#1A9850")
prozent <- function(x) paste0(round(x * 100), " %")

p <- ggplot(tab, aes(x = Anteil, y = Vergleich, fill = Ergebnis, group = Ergebnis)) +
  geom_col(width = 0.65) +
  geom_text(aes(label = Label, colour = Textfarbe), position = position_stack(vjust = 0.5), size = 3.2 * skal) +
  scale_colour_identity() +
  scale_fill_manual(values = farben, breaks = c("schlechter", "gleich", "besser")) +
  scale_x_continuous(labels = prozent, breaks = seq(0, 1, 0.2), expand = expansion(mult = c(0, 0.03))) +
  labs(x = paste0("Anteil der Buchfragen (n = ", nrow(d), ")"), y = NULL, fill = NULL) +
  theme_classic(base_size = 10 * skal) +
  theme(legend.position = "top", legend.justification = c(0.8, 0.5),
        legend.text = element_text(size = 10 * skal, margin = margin(r = 8 * skal, l = 4 * skal)),
        legend.key.size = unit(0.45 * skal, "cm"),
        axis.text = element_text(size = 10 * skal), axis.title.x = element_text(size = 12 * skal))
if (speichern) {
  ggsave("Abb07_Paarvergleiche.png", p, width = breite_cm, height = hoehe_cm, units = "cm", dpi = 600, bg = "white")
} else {
  grid::grid.newpage()
  print(p, vp = grid::viewport(width = grid::unit(breite_cm * skal, "cm"), height = grid::unit(hoehe_cm * skal, "cm")))
}

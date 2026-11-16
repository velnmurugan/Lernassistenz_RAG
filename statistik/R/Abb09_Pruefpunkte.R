# =====================================================================
# Abbildung 9 – Bewertung der Hinweise je Prüfpunkt (269 Hinweise;
# menschliche Bewertung).
# Läuft im jamovi-Modul "Rj Editor" (`data` = geöffnete Tabelle) und in R.
# =====================================================================
if (!is.data.frame(data)) data <- readxl::read_excel("Daten_Beitrag_jamovi.xlsx", sheet = "Daten")
library(ggplot2)
speichern <- FALSE
breite_cm <- 18; hoehe_cm <- 8   # Größe der Abbildung im Beitrag
# Die Abbildung wird immer in Originalgröße gezeichnet. In jamovi (Rj Editor) dafür im Zahnrad-Menü
# "Figure size (px)" Width = 512 und Height = 314 eintragen (1 px = 1/72 Zoll; 18 × 11 cm).
skal <- 1   # Verkleinerungsfaktor für Schrift und Linien (1 = wie im Beitrag)

d <- as.data.frame(data)
d <- d[!is.na(d$H1_korrekt) & as.character(d$H1_korrekt) != "", ]   # nur bewertete Hinweise

pruefpunkte <- c(H1_korrekt = "1 Fachlich korrekt", H2_offen = "2 Lösung bleibt offen",
                 H3_schritt = "3 Nächster Schritt", H4_verstaendlich = "4 Verständlich & nutzbar")
kategorien  <- c(ja = "erfüllt", teilweise = "teilweise (zu vage)", nein = "nicht erfüllt",
                 "nicht entscheidbar" = "nicht entscheidbar")

tab <- do.call(rbind, lapply(names(pruefpunkte), function(k) {
  x <- as.character(d[[k]])
  n <- sapply(names(kategorien), function(u) sum(x == u, na.rm = TRUE))
  data.frame(Pruefpunkt = pruefpunkte[k], Urteil = kategorien, n = as.numeric(n), Anteil = as.numeric(n) / nrow(d))
}))
tab <- tab[tab$n > 0, ]
tab$Pruefpunkt <- factor(tab$Pruefpunkt, levels = rev(pruefpunkte))
tab$Urteil     <- factor(tab$Urteil, levels = rev(kategorien))     # erfüllt links
tab$Label      <- ifelse(tab$n >= 15, tab$n, "")
tab$Textfarbe  <- ifelse(tab$Urteil %in% c("teilweise (zu vage)", "nicht entscheidbar"), "black", "white")

farben  <- c("erfüllt" = "#1A9850", "teilweise (zu vage)" = "#F2B600",
             "nicht erfüllt" = "#D73027", "nicht entscheidbar" = "#B3B3B3")
prozent <- function(x) paste0(round(x * 100), " %")

p <- ggplot(tab, aes(x = Anteil, y = Pruefpunkt, fill = Urteil, group = Urteil)) +
  geom_col(width = 0.65) +
  geom_text(aes(label = Label, colour = Textfarbe), position = position_stack(vjust = 0.5), size = 3.2 * skal) +
  scale_colour_identity() +
  scale_fill_manual(values = farben, breaks = kategorien, drop = FALSE) +
  scale_x_continuous(labels = prozent, breaks = seq(0, 1, 0.2), expand = expansion(mult = c(0, 0.03))) +
  labs(x = paste0("Anteil der Hinweise (n = ", nrow(d), ")"), y = NULL, fill = NULL) +
  theme_classic(base_size = 10 * skal) +
  theme(legend.position = "top", legend.justification = c(0.9, 0.5),
        legend.text = element_text(size = 10 * skal, margin = margin(r = 8 * skal, l = 4 * skal)),
        legend.key.size = unit(0.45 * skal, "cm"),
        axis.text = element_text(size = 10 * skal), axis.title.x = element_text(size = 12 * skal))
if (speichern) {
  ggsave("Abb09_Pruefpunkte.png", p, width = breite_cm, height = hoehe_cm, units = "cm", dpi = 600, bg = "white")
} else {
  grid::grid.newpage()
  print(p, vp = grid::viewport(width = grid::unit(breite_cm * skal, "cm"), height = grid::unit(hoehe_cm * skal, "cm")))
}

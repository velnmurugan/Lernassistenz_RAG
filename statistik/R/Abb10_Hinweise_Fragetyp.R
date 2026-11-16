# =====================================================================
# Abbildung 10 – Anteil starker, akzeptabler und nicht akzeptabler
# Hinweise nach Fragetyp (269 Hinweise; menschliche Bewertung).
# akzeptabel = Prüfpunkte 1, 2, 4 erfüllt und 3 mindestens teilweise;
# stark      = akzeptabel und Prüfpunkt 3 voll erfüllt.
# Läuft im jamovi-Modul "Rj Editor" (`data` = geöffnete Tabelle) und in R.
# =====================================================================
if (!is.data.frame(data)) data <- readxl::read_excel("Daten_Beitrag_jamovi.xlsx", sheet = "Daten")
library(ggplot2)
speichern <- FALSE
breite_cm <- 18; hoehe_cm <- 10   # Größe der Abbildung im Beitrag
# Die Abbildung wird immer in Originalgröße gezeichnet. In jamovi (Rj Editor) dafür im Zahnrad-Menü
# "Figure size (px)" Width = 512 und Height = 314 eintragen (1 px = 1/72 Zoll; 18 × 11 cm).
skal <- 1   # Verkleinerungsfaktor für Schrift und Linien (1 = wie im Beitrag)
label_mensch <- "Human 1"

d <- as.data.frame(data)
d <- d[!is.na(d$H1_korrekt) & as.character(d$H1_korrekt) != "", ]
ja <- function(x) as.character(x) == "ja"
akzeptabel <- ja(d$H1_korrekt) & ja(d$H2_offen) & ja(d$H4_verstaendlich) &
              as.character(d$H3_schritt) %in% c("ja", "teilweise")
stark <- akzeptabel & ja(d$H3_schritt)
d$Klasse <- ifelse(stark, "stark", ifelse(akzeptabel, "akzeptabel (nicht stark)", "nicht akzeptabel"))

typen <- c("Konzept", "Fakt", "Rechnung", "Tabellenabfrage", "Aufzählung")
klassen <- c("stark", "akzeptabel (nicht stark)", "nicht akzeptabel")
gruppen <- c(list(Gesamt = rep(TRUE, nrow(d))),
             setNames(lapply(typen, function(t) as.character(d$Typ) == t), typen))

tab <- do.call(rbind, lapply(names(gruppen), function(g) {
  x <- d$Klasse[gruppen[[g]]]
  n <- sapply(klassen, function(k) sum(x == k))
  data.frame(Gruppe = paste0(g, "\n(n = ", length(x), ")"), Klasse = klassen,
             n = as.numeric(n), Anteil = as.numeric(n) / length(x))
}))
tab$Gruppe    <- factor(tab$Gruppe, levels = rev(unique(tab$Gruppe)))
tab$Klasse    <- factor(tab$Klasse, levels = rev(klassen))       # stark links
tab$Textfarbe <- ifelse(tab$Klasse == "akzeptabel (nicht stark)", "black", "white")

farben  <- c("stark" = "#1A6E3A", "akzeptabel (nicht stark)" = "#7FC97F", "nicht akzeptabel" = "#D73027")
prozent <- function(x) paste0(round(x * 100), " %")

p <- ggplot(tab, aes(x = Anteil, y = Gruppe, fill = Klasse, group = Klasse)) +
  geom_col(width = 0.65) +
  geom_text(aes(label = ifelse(n > 0, n, ""), colour = Textfarbe), position = position_stack(vjust = 0.5), size = 3.2 * skal) +
  scale_colour_identity() +
  scale_fill_manual(values = farben, breaks = klassen) +
  scale_x_continuous(labels = prozent, breaks = seq(0, 1, 0.2), expand = expansion(mult = c(0, 0.03))) +
  labs(x = paste0("Anteil der Hinweise (Bewertung ", label_mensch, ")"), y = NULL, fill = NULL) +
  theme_classic(base_size = 10 * skal) +
  theme(legend.position = "top",
        legend.text = element_text(size = 10 * skal, margin = margin(r = 8 * skal, l = 4 * skal)),
        legend.key.size = unit(0.45 * skal, "cm"),
        axis.text = element_text(size = 10 * skal), axis.title.x = element_text(size = 12 * skal))
if (speichern) {
  ggsave("Abb10_Hinweise_Fragetyp.png", p, width = breite_cm, height = hoehe_cm, units = "cm", dpi = 600, bg = "white")
} else {
  grid::grid.newpage()
  print(p, vp = grid::viewport(width = grid::unit(breite_cm * skal, "cm"), height = grid::unit(hoehe_cm * skal, "cm")))
}

# Rapport de stage — Source LaTeX

## Compiler le rapport

Nécessite une distribution LaTeX (TeX Live / MiKTeX) avec le paquet de
langue française pour babel (`texlive-lang-french` sous Debian/Ubuntu,
inclus par défaut dans la plupart des distributions Windows/Mac comme
MiKTeX ou TeX Live complet).

```bash
pdflatex main.tex
pdflatex main.tex   # 2e passe : table des matières
pdflatex main.tex   # 3e passe : numéros de page définitifs dans la TOC
```

Le PDF déjà compilé (`main.pdf`, 32 pages) est fourni à côté pour
consultation immédiate — recompilez après toute modification du
contenu.

## Où sont les schémas

Les 5 figures générées automatiquement sont dans `diagrams/` (format
PNG, sources éditables : voir `diagrams_sources/` pour les fichiers
`.dot` Graphviz et scripts Python/matplotlib utilisés pour les
produire, si vous souhaitez les régénérer avec des données à jour).

## Ce qu'il reste à compléter

Cherchez `[À COMPLÉTER` dans `main.tex` (encadrés rouges dans le PDF) :
logos, nom de l'école/encadrants, remerciements, plusieurs captures
d'écran (console AWS, Jira, interface Streamlit...). La liste complète
est aussi récapitulée en annexe A.3 du rapport.

Avant la remise finale : régénérer `diagrams/resultats_evaluation.png`
avec les données de votre dernière exécution du harnais d'évaluation
(`evaluation/run_evaluation.py` du projet), si elle diffère de celle
utilisée ici (95,7 %, 22/23).

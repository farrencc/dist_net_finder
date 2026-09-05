#!/bin/sh
# Build the report: pdflatex, bibtex, then pdflatex twice more so the
# bibliography, the table of contents and the cross-references all resolve.
#
# Needs pdflatex with booktabs, listings, hyperref, geometry, microtype,
# xcolor, caption, titlesec, fancyhdr, tabularx, enumitem, float and natbib.
# On Debian/Ubuntu:
#
#   apt-get install texlive-latex-recommended texlive-latex-extra \
#                   texlive-fonts-recommended lmodern
#
# The figures it includes are produced by, from the repository root:
#
#   python docs/report_figures.py
#   cd participant-kit && for e in examples/*.py; do python "$e"; done
set -e
cd "$(dirname "$0")"
pdflatex -interaction=nonstopmode -halt-on-error report.tex > /dev/null
bibtex report > /dev/null || true
pdflatex -interaction=nonstopmode -halt-on-error report.tex > /dev/null
pdflatex -interaction=nonstopmode -halt-on-error report.tex > /dev/null
echo "-> $(pwd)/report.pdf"

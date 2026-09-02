#!/usr/bin/env python3
"""Regenerates CHANGELOG_EN.pdf and CHANGELOG_FR.pdf from their markdown
sources.

Run automatically by build_mac.sh on every build, so the PDF release notes
handed out with the app never drift out of sync with the markdown source -
see the "Changelog" section in CLAUDE.md for the editing convention (turn
each CHANGELOG_*.md's "Unreleased" section into a dated version entry
before bumping trichrome.spec, this script does the rest).

Uses PySide6's own QTextDocument/QPrinter (already a project dependency)
instead of pulling in a separate PDF-generation library.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
LANGUAGES = ("EN", "FR")


def _render(md_path: Path, pdf_path: Path) -> None:
    markdown = md_path.read_text(encoding="utf-8")
    doc = QTextDocument()
    doc.setMarkdown(markdown)

    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(str(pdf_path))
    printer.setPageSize(QPageSize(QPageSize.A4))
    printer.setPageMargins(QMarginsF(18, 16, 18, 16), QPageLayout.Millimeter)

    doc.print_(printer)

    size = pdf_path.stat().st_size if pdf_path.exists() else 0
    print(f"Wrote {pdf_path.relative_to(ROOT)} ({size} bytes)")


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    for lang in LANGUAGES:
        _render(ROOT / f"CHANGELOG_{lang}.md", ROOT / f"CHANGELOG_{lang}.pdf")
    _ = app  # keep the QApplication alive until every print_() has fully run


if __name__ == "__main__":
    main()

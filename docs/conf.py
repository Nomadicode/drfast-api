"""Sphinx configuration for DRFast API."""

project = "DRFast API"
copyright = "2026, DRFast API contributors"
author = "DRFast API contributors"

extensions = ["sphinx.ext.autodoc", "sphinx.ext.napoleon"]
templates_path = ["_templates"]
exclude_patterns: list[str] = []

html_theme = "alabaster"
autodoc_typehints = "description"

"""Sphinx configuration; see "Documentation" in the README for the build command."""

import robonomicsinterface

project = "robonomics-interface"
author = "Pavel Tarasov, Vadim Manaenko"
release = robonomicsinterface.__version__

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
]
myst_heading_anchors = 3
myst_enable_extensions = ["alert"]
exclude_patterns: list[str] = []

autodoc_member_order = "bysource"
autodoc_typehints = "description"
intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}

html_theme = "furo"

from __future__ import annotations

project = "faultcore"
author = "faultcore contributors"

extensions = [
    "myst_parser",
    "sphinxcontrib.mermaid",
]

myst_fence_as_directive = ["mermaid"]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

root_doc = "index"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "alabaster"

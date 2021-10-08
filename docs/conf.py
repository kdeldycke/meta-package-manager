import os
from pathlib import Path

import tomli

project_path = Path(__file__).parent.parent.resolve()

# Fetch general information about the project from pyproject.toml.
toml_path = project_path / "pyproject.toml"
toml_config = tomli.loads(toml_path.read_text())

# Redistribute pyproject.toml config to Sphinx.
project_id = toml_config["tool"]["poetry"]["name"]
version = toml_config["tool"]["poetry"]["version"]
url = toml_config["tool"]["poetry"]["homepage"]
author = ", ".join(
    (a.split("<")[0].strip() for a in toml_config["tool"]["poetry"]["authors"])
)

# Title-case each word of the project ID.
project = " ".join((word.title() for word in project_id.split("-")))
htmlhelp_basename = project_id

release = version

# Addons.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.todo",
    "sphinx.ext.viewcode",
    "sphinx_tabs.tabs",
    # Adds a copy button to code blocks.
    "sphinx_copybutton",
    # Link to GitHub issues and PRs.
    "sphinx_issues",
    "sphinxext.opengraph",
]

master_doc = "index"

# We use our own copyright template instead of the default as the latter strip
# HTML content.
html_show_copyright = False
copyright = (
    f"<a href='https://kevin.deldycke.com'>{author}</a> and <a href='{url}"
    "/graphs/contributors'>contributors</a>"
)
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

nitpicky = True

# We need a recent sphinx because of the last update format.
needs_sphinx = "2.4"
html_last_updated_fmt = "YYYY-MM-dd"
templates_path = ["templates"]

# Both the class’ and the __init__ method’s docstring are concatenated and
# inserted.
autoclass_content = "both"
# Keep the same ordering as in original source code.
autodoc_member_order = "bysource"
autodoc_default_flags = ["members", "undoc-members", "show-inheritance"]

# If true, `todo` and `todoList` produce output, else they produce nothing.
todo_include_todos = True

issues_github_path = f"kdeldycke/{project_id}"

extlinks = {
    "issue": (f"https://github.com/{issues_github_path}/issues/%s", "issue "),
    "pr": (f"https://github.com/{issues_github_path}/pull/%s", "pull request "),
}


html_theme = "furo"
html_title = project

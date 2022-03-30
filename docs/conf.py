import sys
from pathlib import Path

if sys.version_info >= (3, 11):
     import tomllib
 else:
     import tomli as tomllib

project_path = Path(__file__).parent.parent.resolve()

# Fetch general information about the project from pyproject.toml.
toml_path = project_path / "pyproject.toml"
toml_config = tomllib.loads(toml_path.read_text())

# Redistribute pyproject.toml config to Sphinx.
project_id = toml_config["tool"]["poetry"]["name"]
version = release = toml_config["tool"]["poetry"]["version"]
url = toml_config["tool"]["poetry"]["homepage"]
author = ", ".join(
    a.split("<")[0].strip() for a in toml_config["tool"]["poetry"]["authors"]
)

# Title-case each word of the project ID.
project = " ".join(word.title() for word in project_id.split("-"))
htmlhelp_basename = project_id

# Addons.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.todo",
    "sphinx.ext.extlinks",
    "sphinx.ext.viewcode",
    "sphinx_tabs.tabs",
    # Adds a copy button to code blocks.
    "sphinx_copybutton",
    # Link to GitHub issues and PRs.
    "sphinx_issues",
    "sphinxext.opengraph",
    "myst_parser",
    "sphinx_click",
]

master_doc = "index"

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

nitpicky = True

# Both the class’ and the __init__ method’s docstring are concatenated and
# inserted.
autoclass_content = "both"
# Keep the same ordering as in original source code.
autodoc_member_order = "bysource"
autodoc_default_flags = ["members", "undoc-members", "show-inheritance"]

# If true, `todo` and `todoList` produce output, else they produce nothing.
todo_include_todos = True

# GitHub pre-implemented shortcuts.
issues_github_path = f"kdeldycke/{project_id}"

# External reference shortcuts.
github_project = f"https://github.com/{issues_github_path}"
extlinks = {
    "gh": (f"{github_project}/%s", "GitHub: %s"),
}

# Theme config.
html_theme = "furo"
html_title = project
html_logo = "images/logo-square.svg"
html_theme_options = {
    "sidebar_hide_name": True,
}

# Footer content.
html_last_updated_fmt = "%Y-%m-%d"
copyright = f"{author} and contributors"
html_show_copyright = True
html_show_sphinx = False

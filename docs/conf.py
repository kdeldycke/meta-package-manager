# -*- coding: utf-8 -*-

import io
import os
import time

import tomlkit

# Fetch general information about the project from pyproject.toml.
toml_path = os.path.join(os.path.dirname(__file__), '..', 'pyproject.toml')
with io.open(toml_path, 'r') as toml_file:
    toml_config = tomlkit.loads(toml_file.read())

# Redistribute pyproject.toml config to Sphinx.
project_id = toml_config['tool']['poetry']['name']
version = toml_config['tool']['poetry']['version']
url = toml_config['tool']['poetry']['homepage']
author = ', '.join([
    a.split('<')[0].strip() for a in toml_config['tool']['poetry']['authors']])

# Title-case each word of the project ID.
project = ' '.join([word.title() for word in project_id.split('-')])
htmlhelp_basename = project_id

release = version

# Addons.
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.todo',
    'sphinx.ext.viewcode']

master_doc = 'index'

# We use our own copyright template instead of the default as the latter strip
# HTML content.
html_show_copyright = False
copyright = (
    "2016-{}, <a href='https://kevin.deldycke.com'>{}</a> and <a href='{}"
    "/graphs/contributors'>contributors</a>").format(
        time.strftime('%Y'), author, url)

exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

nitpicky = True

# We need a recent sphinx because of the last update format.
needs_sphinx = '2.4'
html_last_updated_fmt = 'YYYY-MM-dd'
templates_path = ['templates']

# Both the class’ and the __init__ method’s docstring are concatenated and
# inserted.
autoclass_content = 'both'
# Keep the same ordering as in original source code.
autodoc_member_order = 'bysource'
autodoc_default_flags = [
    'members',
    'undoc-members',
    'show-inheritance']

# If true, `todo` and `todoList` produce output, else they produce nothing.
todo_include_todos = True

# Use RTD theme both locally and online. Source: https://github.com/snide
# /sphinx_rtd_theme#using-this-theme-locally-then-building-on-read-the-docs
on_rtd = os.environ.get('READTHEDOCS', None) == 'True'
if not on_rtd:
    import sphinx_rtd_theme
    html_theme = 'sphinx_rtd_theme'
    html_theme_path = [sphinx_rtd_theme.get_html_theme_path()]

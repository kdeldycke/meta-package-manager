# -*- coding: utf-8 -*-

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)

import os
import subprocess
import sys
import time


# Fetch general information about the project.
# Source: https://github.com/jaraco/skeleton/blob/skeleton/docs/conf.py
root = os.path.join(os.path.dirname(__file__), '..')
setup_script = os.path.join(root, 'setup.py')
fields = ['--name', '--version', '--url', '--author']
dist_info_cmd = [sys.executable, setup_script] + fields
output_bytes = subprocess.check_output(dist_info_cmd, cwd=root)
project_id, version, url, author = output_bytes.decode(
    'utf-8').strip().split('\n')

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
    "2016-{}, <a href='https://kevin.deldycke.com'>{}</a> and <a href='https:"
    "//github.com/kdeldycke/{}/graphs/contributors'>contributors</a>").format(
        time.strftime('%Y'), author, project_id)

exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

nitpicky = True

# We need a recent sphinx because of the last update format.
needs_sphinx = '1.4'
html_last_updated_fmt = 'YYYY-MM-dd'
templates_path = ['templates']

# Keep the same ordering as in original source code.
autodoc_member_order = 'bysource'

# If true, `todo` and `todoList` produce output, else they produce nothing.
todo_include_todos = True

# Use RTD theme both locally and online. Source: https://github.com/snide
# /sphinx_rtd_theme#using-this-theme-locally-then-building-on-read-the-docs
on_rtd = os.environ.get('READTHEDOCS', None) == 'True'
if not on_rtd:
    import sphinx_rtd_theme
    html_theme = 'sphinx_rtd_theme'
    html_theme_path = [sphinx_rtd_theme.get_html_theme_path()]

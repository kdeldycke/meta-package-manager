# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
# All Rights Reserved.
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

""" Helpers and utilities to render and print content. """

import re
from collections import namedtuple
from functools import partial
from operator import itemgetter
from pathlib import Path

import click
from boltons.strutils import strip_ansi
from cli_helpers.tabular_output import TabularOutputFormatter
from click.core import BaseCommand
from click_log.core import ColorFormatter
from cloup import HelpFormatter, HelpTheme, Style
from simplejson import dumps as json_dumps

from . import CLI_NAME, __version__
from .platform import is_windows
from .version import TokenizedString

# Initialize the table formatter.
table_formatter = TabularOutputFormatter()


# Register all rendering modes for table data.
RENDERING_MODES = {"json"}
RENDERING_MODES.update(table_formatter.supported_formats)
RENDERING_MODES = frozenset(RENDERING_MODES)


# List of fields IDs allowed to be sorted.
SORTABLE_FIELDS = {
    "manager_id",
    "manager_name",
    "package_id",
    "package_name",
    "version",
}


# Extend the predefined theme named tuple with our extra styles.
theme_params = {
    field: Style()
    for field in HelpTheme._fields
    + ("option", "choice", "metavar", "search", "success")
}

# Extend even more with logging styles.
assert set(theme_params).isdisjoint(ColorFormatter.colors)
theme_params.update(
    {
        style_id: Style(**color_params)
        for style_id, color_params in ColorFormatter.colors.items()
    }
)

# Populate theme with all default styles.
HelpExtraTheme = namedtuple(
    "HelpExtraTheme", theme_params.keys(), defaults=theme_params.values()
)


# Set our CLI global theme.
theme = HelpExtraTheme(
    invoked_command=Style(fg="bright_white"),
    heading=Style(fg="bright_blue", bold=True),
    constraint=Style(fg="magenta"),
    col1=Style(fg="cyan"),
    option=Style(fg="cyan"),
    choice=Style(fg="magenta"),
    metavar=Style(fg="bright_black"),
    search=Style(fg="green", bold=True),
    success=Style(fg="green"),
)


# Pre-rendered UI-elements.
OK = theme.success("✓")
KO = theme.error("✘")


class ExtraHelpColorsMixin:
    """Adds extra-keywords highlighting to Click commands.

    This mixin for `click.core.Command`-like classes intercepts the top-level
    helper-generation method to initialize the formatter with dynamic settings.

    This is implemented here to get access to the global context.
    """

    def collect_keywords(self, ctx):
        """Parse click context to collect option names, choices and metavar keywords."""
        options = set()
        choices = set()
        metavars = set()

        # Add user defined help options.
        options.update(ctx.help_option_names)

        # Collect all option names and choice keywords.
        for param in ctx.command.params:
            options.update(param.opts)
            if isinstance(param.type, click.Choice):
                choices.update(param.type.choices)
            if param.metavar:
                metavars.add(param.metavar)

        return options, choices, metavars

    def get_help(self, ctx):
        """Imitates the original `click.core:BaseCommand.get_help()` method but initialize the formatter
        with the list of extra keywords to highlights.
        """
        formatter = ctx.make_formatter()
        (
            formatter.option_words,
            formatter.choice_words,
            formatter.metavar_words,
        ) = self.collect_keywords(ctx)
        self.format_help(ctx, formatter)
        return formatter.getvalue().rstrip("\n")


class HelpExtraFormatter(HelpFormatter):
    """Extends Cloup's custom HelpFormatter to highlights options, choices,
    metavars and default values.

    This is being discussed for upstream integration at:
    * https://github.com/janluke/cloup/issues/97
    * https://github.com/click-contrib/click-help-colors/issues/17
    * https://github.com/janluke/cloup/issues/95
    """

    # Lists of extra keywords to highlight.
    option_words = tuple()
    choice_words = tuple()
    metavar_words = tuple()

    def highlight_extra_keywords(self, help_text):
        """Highlight extra keywoards in help screens based on the theme.

        It is based on regular expressions. While this is not a bullet-proof method, it is good
        enough. After all, help screens are not consumed by machine but are designed for human.
        """

        def colorize(match, style):
            """Re-create the matching string by concatenating all groups, but only
            colorize named groups.
            """
            txt = ""
            for group in match.groups():
                if group in match.groupdict().values():
                    txt += style(group)
                else:
                    txt += group
            return txt

        # Highligh numbers.
        help_text = re.sub(
            r"(\s)(?P<colorize>-?\d+)",
            partial(colorize, style=self.theme.choice),
            help_text,
        )

        # Highlight CLI name.
        help_text = re.sub(
            fr"(\s)(?P<colorize>{CLI_NAME})",
            partial(colorize, style=self.theme.invoked_command),
            help_text,
        )

        # Highligh sections.
        help_text = re.sub(
            r"^(?P<colorize>\S[\S+ ]+)(:)",
            partial(colorize, style=self.theme.heading),
            help_text,
            flags=re.MULTILINE,
        )

        # Highlight keywords.
        for matching_keywords, style in (
            (sorted(self.option_words), self.theme.option),
            (sorted(self.choice_words, reverse=True), self.theme.choice),
            (sorted(self.metavar_words, reverse=True), self.theme.metavar),
        ):
            for keyword in matching_keywords:
                # Accounts for text wrapping after a dash.
                keyword = keyword.replace("-", "-\\s*")
                help_text = re.sub(
                    fr"([\s\[\|\(])(?P<colorize>{keyword})",
                    partial(colorize, style=style),
                    help_text,
                )

        return help_text

    def getvalue(self):
        """Wrap original `Click.HelpFormatter.getvalue()` to force extra-colorization on rendering."""
        help_text = super().getvalue()
        return self.highlight_extra_keywords(help_text)


def json(data):
    """Utility function to render data structure into pretty printed JSON.

    Also care of internal objects like `TokenizedString` and `Path`:
    """

    def serialize_objects(obj):
        if isinstance(obj, (TokenizedString, Path)):
            return str(obj)
        raise TypeError(repr(obj) + " is not JSON serializable.")

    return json_dumps(
        data,
        sort_keys=True,
        indent=4,
        separators=(",", ": "),
        default=serialize_objects,
    )


def print_table(header_defs, rows, sort_key=None, color=True):
    """Utility to print a table and sort its content."""
    # Do not print anything, not even table headers if no rows.
    if not rows:
        return

    header_labels = (click.style(label, bold=True) for label, _ in header_defs)

    # Check there is no duplicate column IDs.
    header_ids = [col_id for _, col_id in header_defs if col_id]
    assert len(header_ids) == len(set(header_ids))

    # Default sorting follows the order of headers.
    sort_order = list(range(len(header_defs)))

    # Move the sorting key's index in the front of priority.
    if sort_key and sort_key in header_ids:
        # Build an index of column id's position.
        col_index = {col_id: i for i, (_, col_id) in enumerate(header_defs) if col_id}
        sort_column_index = col_index[sort_key]
        sort_order.remove(sort_column_index)
        sort_order.insert(0, sort_column_index)

    def sort_method(line):
        """Serialize line's content for natural sorting.

        1. Extract each cell value in the order provided by `sort_order`;
        2. Strip terminal color formating;
        3. Then tokenize each cell's content for user-friendly natural sorting.
        """
        sorting_key = []
        for cell in itemgetter(*sort_order)(line):
            if isinstance(cell, TokenizedString):
                key = cell
            else:
                key = TokenizedString(strip_ansi(cell))
            sorting_key.append(key)
        return tuple(sorting_key)

    for line in table_formatter.format_output(
        sorted(rows, key=sort_method), header_labels, disable_numparse=True
    ):
        if is_windows():
            line = line.encode("utf-8")
        click.echo(line, color=color)


def print_stats(data):
    """Print statistics."""
    manager_stats = {infos["id"]: len(infos["packages"]) for infos in data.values()}
    total_installed = sum(manager_stats.values())
    per_manager_totals = ", ".join(
        (
            f"{k}: {v}"
            for k, v in sorted(manager_stats.items(), key=itemgetter(1), reverse=True)
        )
    )
    if per_manager_totals:
        per_manager_totals = f" ({per_manager_totals})"
    plural = "s" if total_installed > 1 else ""
    click.echo(f"{total_installed} package{plural} total{per_manager_totals}.")

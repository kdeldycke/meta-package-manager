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

""" Helpers and utilities to apply ANSI coloring to terminal content. """

import re
from collections import namedtuple
from functools import partial

import click
from click_log.core import ColorFormatter
from cloup import HelpFormatter, HelpTheme, Style

from . import CLI_NAME, __version__

# Extend the predefined theme named tuple with our extra styles.
theme_params = {
    field: Style()
    for field in HelpTheme._fields
    + ("subheading", "option", "choice", "metavar", "search", "success")
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
    subheading=Style(fg="blue"),
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

        # Split between shorts and long options
        long_options = set()
        short_options = set()
        for option in options:
            if option.startswith("--"):
                long_options.add(option)
            else:
                short_options.add(option)

        return long_options, short_options, choices, metavars

    def get_help(self, ctx):
        """Imitates the original `click.core:BaseCommand.get_help()` method but initialize the formatter
        with the list of extra keywords to highlights.
        """
        formatter = ctx.make_formatter()
        (
            formatter.long_options,
            formatter.short_options,
            formatter.choices,
            formatter.metavars,
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
    long_options = set()
    short_options = set()
    choices = set()
    metavars = set()

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
            (sorted(self.long_options, reverse=True), self.theme.option),
            (sorted(self.short_options), self.theme.option),
            (sorted(self.choices, reverse=True), self.theme.choice),
            (sorted(self.metavars, reverse=True), self.theme.metavar),
        ):
            for keyword in matching_keywords:
                # Accounts for text wrapping after a dash.
                keyword = keyword.replace("-", "-\\s*")
                help_text = re.sub(
                    fr"([\s\[\|\(])(?P<colorize>{keyword})(\W)",
                    partial(colorize, style=style),
                    help_text,
                )

        return help_text

    def getvalue(self):
        """Wrap original `Click.HelpFormatter.getvalue()` to force extra-colorization on rendering."""
        help_text = super().getvalue()
        return self.highlight_extra_keywords(help_text)

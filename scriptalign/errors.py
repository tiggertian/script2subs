"""User-fixable errors, surfaced as messages in the CLI and UI."""


class ScriptError(Exception):
    """The scripts, timings or paths need attention from the user."""

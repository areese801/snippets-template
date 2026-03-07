"""
Shared test helpers for snippet repository tests.
"""

import json
import re
from unittest.mock import patch

import pytest


def extract_json(text):
    """
    Extract JSON object from text that may contain log lines.
    """
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No JSON found in: {text!r}")


def run_cli(main_fn, argv, capsys):
    """
    Run a CLI main() function and return (exit_code, parsed_json_output).

    Patches sys.argv, expects SystemExit, captures stdout, and parses JSON.
    Uses extract_json to handle mixed log/JSON output.
    """
    with patch("sys.argv", argv):
        with pytest.raises(SystemExit) as exc:
            main_fn()
    stdout = capsys.readouterr().out
    return exc.value.code, extract_json(stdout)

"""Smoke tests for the CLI surface (SPEC §15): every command must resolve."""

from __future__ import annotations

from typer.testing import CliRunner

from nutridb.cli import app

runner = CliRunner()

ALL_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("sources", "sync"),
    ("sources", "fetch"),
    ("sources", "audit"),
    ("extract",),
    ("vocab", "check"),
    ("link",),
    ("i18n", "build"),
    ("i18n", "review"),
    ("merge",),
    ("derive",),
    ("qa",),
    ("package",),
    ("build",),
    ("diff",),
    ("serve",),
    ("explorer", "dev"),
)


def test_help_exits_zero() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    commands = (
        "sources",
        "extract",
        "vocab",
        "i18n",
        "merge",
        "package",
        "build",
        "serve",
        "explorer",
    )
    for line in commands:
        assert line in result.stdout


def test_version_prints_semver() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "nutridb" in result.stdout
    assert result.stdout.count(".") >= 2


def test_every_command_resolves() -> None:
    """Every registered command must exist in the CLI (fail high, no typos)."""
    for command in ALL_COMMANDS:
        result = runner.invoke(app, [*command, "--help"])
        assert result.exit_code == 0, f"{'/'.join(command)} --help failed: {result.output}"


def test_sources_audit_reports_ciqual() -> None:
    result = runner.invoke(app, ["sources", "audit"])
    assert result.exit_code == 0
    assert "ciqual" in result.stdout
    assert "etalab-2.0" in result.stdout
    assert "NO" in result.stdout or "pinned" in result.stdout


def test_unimplemented_commands_fail_high() -> None:
    for command in (("merge",), ("qa",)):
        result = runner.invoke(app, [*command])
        assert result.exit_code == 2
        assert "not implemented" in result.output


def test_sources_fetch_unknown_id_fails() -> None:
    result = runner.invoke(app, ["sources", "fetch", "does-not-exist"])
    assert result.exit_code != 0
    assert "does-not-exist" in result.output

"""The nutridb command-line interface (SPEC §15)."""

from __future__ import annotations

import rich.table
import rich.text
import structlog
import typer

from nutridb import __version__
from nutridb.logging import configure_logging
from nutridb.sources.download import fetch_unpinned, sync_sources
from nutridb.sources.registry import ArtifactProfile, load_registry

log = structlog.get_logger()

app = typer.Typer(
    name="nutridb",
    help="NUTRIDB — base de dados aberta de composicao alimentar (SPEC.md).",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"nutridb {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        None, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."
    ),
    verbose: int = typer.Option(
        0, "--verbose", "-v", count=True, help="Increase logging verbosity."
    ),
) -> None:
    """Common CLI entrypoint."""
    configure_logging(verbosity=verbose)
    ctx.obj = {}


# ── sources ───────────────────────────────────────────────────────────────────

sources_app = typer.Typer(name="sources", help="Download, verify and audit data sources.")
app.add_typer(sources_app, name="sources")


@sources_app.command("sync")
def sources_sync(
    source: str | None = typer.Option(
        None, "--source", "-s", help="Only synchronize this source id."
    ),
) -> None:
    """Download missing dumps and verify every pinned sha256 (fail high)."""
    registry = load_registry()
    sync_sources(registry, source=source)


@sources_app.command("fetch")
def sources_fetch(
    source: str = typer.Argument(help="Source id to fetch (e.g. 'ciqual')."),
) -> None:
    """Download an unpinned source and print the sha256 to pin in the registry."""
    registry = load_registry()
    try:
        entry = registry.by_id(source)
    except KeyError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    if entry.sha256 is not None or entry.files:
        typer.echo(
            f"{source}: already pinned (sha256 = {entry.sha256!r}, files = {len(entry.files)})"
        )
        raise typer.Exit()
    digest = fetch_unpinned(entry)
    typer.echo("Downloaded. Review before pinning:")
    typer.echo(f'  sha256 = "{digest}"')
    if entry.filename is None:
        typer.echo('  filename = "..."  # basename of the official file')
    typer.echo("Add these to sources/registry.toml and run `nutridb sources sync`.")


@sources_app.command("audit")
def sources_audit() -> None:
    """Print the license/artifact audit report derived from the registry."""
    registry = load_registry()
    table = rich.table.Table(title="Source registry audit", title_justify="left")
    for column in ("id", "license", "version", "share-alike", "commercial", "artifacts", "pinned"):
        table.add_column(column, style="bold" if column in ("id", "license") else None)
    for entry in sorted(registry.sources.values(), key=lambda s: s.id):
        table.add_row(
            entry.id,
            entry.license_id,
            entry.version,
            "yes" if entry.share_alike else "no",
            "yes" if entry.commercial_use else ("no" if entry.commercial_use is False else "?"),
            ",".join(entry.artifacts),
            "yes" if (entry.sha256 or entry.files) else "NO",
        )
    console = rich.console.Console()
    console.print(table)
    for profile in (ArtifactProfile.CORE, ArtifactProfile.EXTENDED, ArtifactProfile.LITE):
        compatible = registry.compatible_with(profile)
        label = rich.text.Text(f"{profile}: {len(compatible)} source(s)")
        console.print(label)


# ── pipeline ──────────────────────────────────────────────────────────────────


def _not_implemented(phase: str, purpose: str) -> None:
    """Fail high: skeleton commands are never silent no-ops."""
    typer.secho(f"not implemented yet (phase {phase}) — {purpose}", fg=typer.colors.YELLOW)
    raise typer.Exit(code=2)


@app.command("extract")
def extract(
    source: str | None = typer.Option(None, "--source", "-s", help="Only extract this source id."),
) -> None:
    """Extract raw source dumps into canonical intermediates."""
    _not_implemented("F1.2", f"extract raw dump for {source or 'all sources'}")


vocab_app = typer.Typer(name="vocab", help="Validate the canonical vocabulary (SPEC §5).")
app.add_typer(vocab_app, name="vocab")


@vocab_app.command("check")
def vocab_check() -> None:
    """Validate vocabulary invariant checks and report counts (fail high)."""
    from nutridb.paths import project_root
    from nutridb.vocab import check_vocabulary

    report = check_vocabulary(project_root())
    if report.errors:
        console = rich.console.Console()
        for error in report.errors:
            console.print(rich.text.Text(error, style="red"))
        raise typer.Exit(code=1)
    table = rich.table.Table(title="Vocabulary check", title_justify="left")
    table.add_column("file")
    table.add_column("rows", justify="right")
    for name, count in report.counts.items():
        table.add_row(name, str(count))
    rich.console.Console().print(table)
    typer.echo("vocabulary OK")


@app.command("link")
def link() -> None:
    """Entity resolution: blocking, signals, adjudication (F3)."""
    _not_implemented("F3", "entity resolution")


i18n_app = typer.Typer(name="i18n", help="Multilingual label pipeline (SPEC §7).")
app.add_typer(i18n_app, name="i18n")


@i18n_app.command("build")
def i18n_build() -> None:
    """Compose labels per locale with status and fallback chains (F4)."""
    _not_implemented("F4", "label composition")


@i18n_app.command("review")
def i18n_review() -> None:
    """Export the human review queue as reviewable patches (F4)."""
    _not_implemented("F4", "translation review queue")


@app.command("merge")
def merge() -> None:
    """Merge values per concept with priorities (F5)."""
    _not_implemented("F5", "source priority merge")


@app.command("derive")
def derive() -> None:
    """Apply derivations: retention, yield, densities, portions (F5)."""
    _not_implemented("F5", "derivations")


@app.command("qa")
def qa() -> None:
    """Run the quality suite and emit an HTML report (F6)."""
    _not_implemented("F6", "quality suite")


@app.command("package")
def package(
    profile: str = typer.Option("core", "--profile", help="core | extended | lite"),
) -> None:
    """Package the database into release artefacts (F7)."""
    _not_implemented("F7", f"package profile {profile}")


@app.command("build")
def build() -> None:
    """Run the full deterministic pipeline (SPEC §16)."""
    _not_implemented("F1.10", "full build orchestration")


@app.command("diff")
def diff(previous: str, current: str) -> None:
    """Report value-level differences between two builds."""
    _not_implemented("F8", f"diff {previous} {current}")


@app.command("serve")
def serve() -> None:
    """Serve the local API (F9)."""
    _not_implemented("F9", "local API server")


explorer_app = typer.Typer(name="explorer", help="NUTRIDB Explorer (SPEC §12).")
app.add_typer(explorer_app, name="explorer")


@explorer_app.command("dev")
def explorer_dev() -> None:
    """Dev server for the explorer web app."""
    _not_implemented("F1.8b", "explorer dev server")


if __name__ == "__main__":
    app()

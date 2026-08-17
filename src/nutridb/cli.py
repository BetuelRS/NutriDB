"""The nutridb command-line interface (SPEC §15)."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import TYPE_CHECKING, NoReturn

import rich.table
import rich.text
import structlog
import typer

from nutridb import __version__
from nutridb.logging import configure_logging
from nutridb.paths import project_root
from nutridb.sources.download import fetch_unpinned, sync_sources
from nutridb.sources.registry import ArtifactProfile, load_registry

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

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


def _not_implemented(phase: str, purpose: str) -> NoReturn:
    """Fail high: skeleton commands are never silent no-ops."""
    typer.secho(f"not implemented yet (phase {phase}) — {purpose}", fg=typer.colors.YELLOW)
    raise typer.Exit(code=2)


@app.command("extract")
def extract(
    source: str | None = typer.Option(None, "--source", "-s", help="Only extract this source id."),
) -> None:
    """Extract raw source dumps into the shared intermediate contract (ADR-0005)."""
    from nutridb.paths import paths
    from nutridb.sources.registry import load_registry

    base = paths()
    registry = load_registry()
    ids = [source] if source is not None else sorted(registry.sources)
    reports: dict[str, dict[str, int]] = {}
    for source_id in ids:
        extractor = _EXTRACTORS.get(source_id)
        if extractor is None:
            _not_implemented("F2+", f"extractor for source {source_id!r}")
        reports[source_id] = extractor(
            base["cache"] / source_id, base["build"] / "intermediates" / source_id
        )
        table = rich.table.Table(title=f"{source_id} extraction", title_justify="left")
        table.add_column("item")
        table.add_column("count", justify="right")
        for name, count in reports[source_id].items():
            table.add_row(name, str(count))
        rich.console.Console().print(table)
    typer.echo("extract OK")


_EXTRACTORS: dict[str, Callable[[Path, Path], dict[str, int]]] = {}


def _register_extractors() -> None:
    """Lazy per-source extractor registry (one import per extractor)."""
    from nutridb.sources.ciqual import extract as extract_ciqual
    from nutridb.sources.insa import extract as extract_insa

    _EXTRACTORS["ciqual"] = extract_ciqual
    _EXTRACTORS["insa"] = extract_insa


_register_extractors()


@app.command("transform")
def transform(
    source: str | None = typer.Option(
        None, "--source", "-s", help="Only transform this source id."
    ),
) -> None:
    """Transform typed intermediates into the canonical dataset (SPEC §8)."""
    if source is not None:
        _not_implemented("F2", "per-source transform — the transform is source-agnostic")
    from nutridb.paths import paths
    from nutridb.transform import TransformError
    from nutridb.transform import transform as run_transform

    base = paths()
    try:
        report = run_transform(
            base["build"] / "intermediates",
            base["build"] / "canonical",
            base["root"],
        )
    except TransformError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    table = rich.table.Table(title="Canonical transform (all sources)", title_justify="left")
    table.add_column("item")
    table.add_column("count", justify="right")
    for name, count in report.items():
        table.add_row(name, str(count))
    rich.console.Console().print(table)
    typer.echo("transform OK")


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
    """Compose labels per locale with status (SPEC §7, D7; F1-lite)."""
    from nutridb.i18n import I18nError
    from nutridb.i18n import build as run_build
    from nutridb.paths import paths

    base = paths()
    canonical = base["build"] / "canonical"
    try:
        report = run_build(canonical, base["root"])
    except I18nError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    table = rich.table.Table(title="i18n labels (F1-lite)", title_justify="left")
    table.add_column("item")
    table.add_column("count", justify="right")
    for name, count in report.items():
        table.add_row(name, str(count))
    rich.console.Console().print(table)
    typer.echo("i18n OK")


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
    """Package the canonical dataset into release artefacts (F7, §8)."""
    if profile != "core":
        _not_implemented("F7", f"package profile {profile}")
    from nutridb.package import PackageError
    from nutridb.package import package as run_package
    from nutridb.paths import paths

    base = paths()
    try:
        info = run_package(
            base["build"] / "canonical",
            base["vocab"],
            base["build"] / "artifacts",
            base["root"],
        )
    except PackageError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    table = rich.table.Table(title=f"package {info['artifact']}", title_justify="left")
    table.add_column("item")
    table.add_column("count", justify="right")
    table.add_row("artifact", info["path"])
    table.add_row("size_bytes", f"{info['size_bytes']:,}")
    table.add_row("page_size", str(info["page_size"]))
    table.add_row("integrity", info["integrity"])
    for name, count in info["tables"].items():
        table.add_row(name, f"{count:,}")
    rich.console.Console().print(table)
    typer.echo("package OK")


@app.command("build")
def build() -> None:
    """Run the full deterministic pipeline (SPEC §16, P10).

    Chains extract -> transform -> i18n build -> package core; any stage
    failure aborts the build (fail high, P9). Requires the source cache:
    run `uv run nutridb sources sync` first.
    """
    from nutridb.i18n import I18nError
    from nutridb.i18n import build as build_labels
    from nutridb.package import PackageError
    from nutridb.package import package as run_package
    from nutridb.paths import paths
    from nutridb.sources.registry import load_registry
    from nutridb.transform import TransformError
    from nutridb.transform import transform as run_transform

    base = paths()
    registry = load_registry()
    try:
        extract_reports: dict[str, dict[str, int]] = {}
        for source_id in sorted(registry.sources):
            extractor = _EXTRACTORS.get(source_id)
            if extractor is None:
                continue  # registered sources without an extractor are not built
            extract_reports[source_id] = extractor(
                base["cache"] / source_id, base["build"] / "intermediates" / source_id
            )
        transform_report = run_transform(
            base["build"] / "intermediates",
            base["build"] / "canonical",
            base["root"],
        )
        build_labels(base["build"] / "canonical", base["root"])
        package_info = run_package(
            base["build"] / "canonical",
            base["vocab"],
            base["build"] / "artifacts",
            base["root"],
        )
    except (TransformError, I18nError, PackageError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.secho(f"{type(exc).__name__}: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    table = rich.table.Table(title="nutridb build (P10)", title_justify="left")
    table.add_column("stage")
    table.add_column("result", justify="right")
    for source_id, report in extract_reports.items():
        for name, count in report.items():
            table.add_row(f"extract {source_id} {name}", str(count))
    for name, count in transform_report.items():
        table.add_row(f"transform {name}", str(count))
    table.add_row("artifact", package_info["artifact"])
    table.add_row("size_bytes", f"{package_info['size_bytes']:,}")
    table.add_row("integrity", package_info["integrity"])
    rich.console.Console().print(table)
    typer.echo("build OK")


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


def _run_npm(*args: str) -> None:
    """Run an npm script in explorer/ with the repo root exported (vite middleware)."""
    explorer_dir = project_root() / "explorer"
    if not (explorer_dir / "package.json").is_file():
        raise typer.BadParameter(f"explorer app missing at {explorer_dir}")
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        raise typer.BadParameter("npm not found — explorer requires Node.js >= 20")
    env = os.environ.copy()
    env["NUTRIDB_ROOT"] = str(project_root())
    result = subprocess.run([npm, *args], cwd=explorer_dir, env=env)
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


@explorer_app.command("dev")
def explorer_dev() -> None:
    """Dev server for the explorer web app (F1.8b; serves /artifacts from the build)."""
    _run_npm("run", "dev")


@explorer_app.command("build")
def explorer_build() -> None:
    """Build the explorer static app (tsc + vite) into explorer/dist/ (F1.8b)."""
    _run_npm("run", "build")


if __name__ == "__main__":
    app()

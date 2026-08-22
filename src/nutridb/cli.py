"""The nutridb command-line interface (SPEC §15)."""

from __future__ import annotations

import csv
import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, NoReturn

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


def _extract_inputs(base: dict[str, Path], source_id: str) -> list[Path]:
    """Every input the extract stage for `source_id` depends on."""
    files: list[Path] = [base["registry"], base["cache"] / source_id]
    files.extend(sorted((project_root() / "src" / "nutridb" / "sources").glob("*.py")))
    return files


def _transform_inputs(base: dict[str, Path]) -> list[Path]:
    """Every input the transform stage depends on."""
    files: list[Path] = [
        base["registry"],
        base["build"] / "intermediates",
        base["mappings"],
        base["vocab"],
    ]
    root = project_root()
    files.extend(
        [
            root / "src" / "nutridb" / "transform.py",
            root / "src" / "nutridb" / "identity" / "__init__.py",
            root / "src" / "nutridb" / "identity" / "matching.py",
        ]
    )
    return files


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


link_app = typer.Typer(
    name="link",
    help="Entity resolution: matcher and human adjudication (SPEC §6).",
    invoke_without_command=True,
    no_args_is_help=False,
)
app.add_typer(link_app, name="link")


@link_app.callback()
def link(
    ctx: typer.Context,
    write: bool = typer.Option(True, help="Write mappings/links.csv (P8 adjudication record)"),
) -> None:
    """Entity resolution: blocking, signals, adjudication (F3).

    ``nutridb link`` runs the matcher (automatic finals + review queue);
    ``nutridb link review`` lists the human queue and applies decisions.
    Runs blocking + signals over the pinned intermediates and the
    bilingual dictionary, writes the adjudication record to
    ``mappings/links.csv`` (automatic finals + review queue; human
    ``adjudicated`` decisions are preserved) and reports precision /
    recall against the hand-labelled golden set.
    """
    if ctx.invoked_subcommand is not None:
        return
    from nutridb.identity.matching import (
        _status,
        evaluate,
        match_foods,
        resolve_one_to_one,
        write_links_csv,
    )
    from nutridb.paths import paths

    base = paths()
    proposals = match_foods(base["build"] / "intermediates", base["root"])
    autos = [p for p in proposals if _status(p) == "automatic"]
    review = [p for p in proposals if _status(p) == "review"]
    finals = len(resolve_one_to_one(autos))

    table = rich.table.Table(title="Identity resolution (F3)", title_justify="left")
    table.add_column("signal")
    table.add_column("count", justify="right")
    table.add_row("candidates", str(len(proposals)))
    table.add_row("automatic finals", str(finals))
    table.add_row("review queue", str(len(review)))
    rich.console.Console().print(table)

    if write:
        links_csv = base["root"] / "mappings" / "links.csv"
        rows = write_links_csv(proposals, links_csv, preserve=links_csv)
        typer.echo(f"links.csv: {rows} rows (automatic + review + preserved adjudicated)")

    golden = base["root"] / "tests" / "golden" / "identity_pairs.csv"
    if golden.is_file():
        metrics = evaluate(proposals, golden)
        table = rich.table.Table(title="Golden evaluation (SPEC F3)", title_justify="left")
        table.add_column("metric")
        table.add_column("value", justify="right")
        for key in (
            "golden_true",
            "golden_false",
            "true_positives",
            "false_positives",
            "false_negatives",
            "auto_finals",
            "review_golden_true",
            "precision",
            "recall",
            "recall_confirmed",
            "food_recall",
        ):
            value = metrics[key]
            table.add_row(key, f"{value:.4f}" if isinstance(value, float) else str(value))
        rich.console.Console().print(table)
        if metrics["precision"] < 0.98 or metrics["recall"] < 0.90:
            raise typer.Exit(code=1)
    typer.echo("link OK")


@link_app.command("review")
def link_review(
    apply: Annotated[
        Path | None,
        typer.Option(
            "--apply",
            exists=True,
            dir_okay=False,
            help="Apply human decisions from a CSV (insa_code,ciqual_code,decision,justification)",
        ),
    ] = None,
    limit: int = typer.Option(50, "--limit", help="Rows shown in the listing (0 = all)"),
) -> None:
    """List the human adjudication queue and apply decisions (SPEC §6.3).

    Listing reads the pending ``review`` pairs from ``mappings/links.csv``
    (the P8 record) and joins proposal context (names, similarity, score)
    from the matcher. ``--apply`` consumes a CSV with columns
    ``insa_code,ciqual_code,decision,justification`` (decision
    ``accepted`` | ``rejected``; justification mandatory for accepted) and
    rewrites the record deterministically.
    """
    from nutridb.identity.matching import (
        LinkError,
        apply_link_decisions,
        match_foods,
        review_pairs,
    )
    from nutridb.paths import paths

    base = paths()
    links_csv = base["root"] / "mappings" / "links.csv"
    if not links_csv.is_file():
        typer.secho(f"links.csv missing: {links_csv}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    if apply is not None:
        try:
            decisions: list[tuple[str, str, str, str]] = []
            with apply.open(encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    decisions.append(
                        (
                            row["insa_code"].strip(),
                            row["ciqual_code"].strip(),
                            row["decision"].strip(),
                            (row.get("justification") or "").strip(),
                        )
                    )
            report = apply_link_decisions(links_csv, decisions)
        except (LinkError, KeyError, ValueError) as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from exc
        table = rich.table.Table(title="Adjudication applied", title_justify="left")
        table.add_column("item")
        table.add_column("count", justify="right")
        for key, value in report.items():
            table.add_row(key, str(value))
        rich.console.Console().print(table)
        typer.echo("link review OK")
        return

    proposals = {
        (p.insa_code, p.ciqual_code): p
        for p in match_foods(base["build"] / "intermediates", base["root"])
    }
    pairs = review_pairs(links_csv)
    table = rich.table.Table(title="Adjudication queue (SPEC §6.3)", title_justify="left")
    table.add_column("insa")
    table.add_column("ciqual")
    table.add_column("alimento (INSA)")
    table.add_column("aliment (CIQUAL)")
    table.add_column("sim")
    table.add_column("score")
    shown = pairs if limit == 0 else pairs[:limit]
    for insa_code, ciqual_code in shown:
        proposal = proposals.get((insa_code, ciqual_code))
        if proposal is None:
            table.add_row(insa_code, ciqual_code, "?", "?", "?", "?")
            continue
        table.add_row(
            insa_code,
            ciqual_code,
            proposal.pt_name,
            proposal.cq_name,
            f"{proposal.sim:.2f}",
            f"{proposal.score:.2f}",
        )
    rich.console.Console().print(table)
    typer.echo(
        f"{len(pairs)} pairs in the review queue" + (f" (showing {len(shown)})" if limit else "")
    )


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
def i18n_review(
    apply: bool = typer.Option(
        False, "--apply", help="write approved candidates to i18n/labels/reviewed_<locale>.csv"
    ),
) -> None:
    """List the human review queue and apply approved decisions (F4, ADR-0006 §3.4).

    Queue: i18n/review_queue/<locale>.csv with columns
    (ref_kind, ref, label, candidate_status); approved rows land in
    i18n/labels/reviewed_<locale>.csv, consumed by `i18n build` as
    curated overrides (highest priority).
    """
    from nutridb.i18n import I18nError, load_locales
    from nutridb.paths import paths

    base = paths()
    root = base["root"]
    active = load_locales(root / "i18n" / "locales.toml")["active"]
    queue_dir = root / "i18n" / "review_queue"
    labels_dir = root / "i18n" / "labels"
    queue_dir.mkdir(exist_ok=True)
    labels_dir.mkdir(exist_ok=True)
    total = 0
    for locale in active:
        path = queue_dir / f"{locale}.csv"
        if not path.is_file():
            continue
        lines = [
            ln for ln in path.open(encoding="utf-8", newline="") if not ln.lstrip().startswith("#")
        ]
        reader = csv.DictReader(lines)
        if reader.fieldnames != ["ref_kind", "ref", "label", "candidate_status"]:
            raise I18nError(f"{path}: header does not match expected columns")
        candidates = [dict(row) for row in reader]
        if not candidates:
            continue
        total += len(candidates)
        approved = [
            (r["ref_kind"], r["ref"], r["label"])
            for r in candidates
            if r["candidate_status"] == "approved"
        ]
        rejected = sum(1 for r in candidates if r["candidate_status"] == "rejected")
        bad = [r for r in candidates if r["candidate_status"] not in ("approved", "rejected")]
        if bad:
            raise I18nError(f"{path}: invalid candidate_status in {bad}")
        table = rich.table.Table(title=f"review queue {locale}", title_justify="left")
        table.add_column("ref_kind")
        table.add_column("ref")
        table.add_column("label")
        table.add_column("status")
        for r in sorted(candidates, key=lambda r: (r["ref_kind"], r["ref"])):
            table.add_row(r["ref_kind"], r["ref"], r["label"], r["candidate_status"])
        rich.console.Console().print(table)
        if apply and approved:
            out = labels_dir / f"reviewed_{locale}.csv"
            with out.open("w", encoding="utf-8", newline="") as fh:
                fh.write(
                    "# Decisoes de revisao humana (CLI `i18n review --apply`); "
                    "consumidas pelo build como curated (ADR-0006).\n"
                )
                writer = csv.writer(fh)
                writer.writerow(("ref_kind", "ref", "label"))
                writer.writerows(sorted(approved))
            typer.echo(
                f"reviewed {locale}: {len(approved)} approved -> {out.name}, {rejected} rejected"
            )
    if total == 0:
        typer.echo("review queue empty: all labels are native/official/curated at birth (P7)")
        return
    typer.echo(f"review total: {total} candidates")


@app.command("merge")
def merge() -> None:
    """Merge values per concept with priorities (SPEC §9, F5)."""
    from nutridb.merge import MergeError
    from nutridb.merge import merge as run_merge
    from nutridb.paths import paths

    base = paths()
    try:
        report = run_merge(base["build"] / "canonical", base["root"])
    except MergeError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    table = rich.table.Table(title="merge (SPEC §9)", title_justify="left")
    table.add_column("item")
    table.add_column("count", justify="right")
    for name, count in report.items():
        table.add_row(name, str(count))
    rich.console.Console().print(table)
    typer.echo("merge OK")


@app.command("derive")
def derive() -> None:
    """Apply derivations: retention, yield, densities, portions (SPEC §10, F5)."""
    from nutridb.derive import DeriveError
    from nutridb.derive import derive as run_derive
    from nutridb.paths import paths

    base = paths()
    try:
        report = run_derive(base["build"] / "canonical", base["root"])
    except DeriveError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    table = rich.table.Table(title="derive (SPEC §10)", title_justify="left")
    table.add_column("item")
    table.add_column("count", justify="right")
    for name, count in report.items():
        table.add_row(name, str(count))
    rich.console.Console().print(table)
    typer.echo("derive OK")


@app.command("qa")
def qa() -> None:
    """Run the quality suite and emit an HTML report (SPEC §11, F6)."""
    import io
    import sys
    import time

    from nutridb.paths import paths
    from nutridb.quality import QualityError, run_quality, write_report

    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    base = paths()
    artifact = base["build"] / "artifacts" / "nutridb-core-0.1.0.sqlite"
    started = time.perf_counter()
    try:
        findings = run_quality(
            base["build"] / "canonical",
            base["vocab"],
            base["root"],
            artifact if artifact.is_file() else None,
        )
    except QualityError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    duration = time.perf_counter() - started
    report_dir = base["build"] / "qa"
    write_report(report_dir, findings, artifact if artifact.is_file() else None, duration)

    console = rich.console.Console()
    table = rich.table.Table(title="qa (SPEC §11)", title_justify="left")
    table.add_column("severidade")
    table.add_column("check")
    table.add_column("detalhe")
    table.add_column("n", justify="right")
    colors = {"error": "red", "warning": "yellow", "info": "blue"}
    for finding in findings:
        table.add_row(
            f"[{colors[finding.severity]}]{finding.severity}",
            finding.check,
            finding.detail,
            str(finding.count),
        )
    console.print(table)
    counts = {"error": 0, "warning": 0, "info": 0}
    for finding in findings:
        counts[finding.severity] += 1
    typer.echo(
        "qa report: "
        f"{report_dir / 'report.html'} ({(report_dir / 'report.html').stat().st_size:,} B)"
    )
    typer.echo(f"qa metrics: {report_dir / 'metrics.json'}")
    if counts["error"]:
        typer.secho(
            f"qa: {counts['error']} error(s) — release bloqueado (SPEC §11)",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    typer.echo("qa OK")


@app.command("export")
def export(
    table: str = typer.Option("all", "--table", help="canonical table name or 'all'"),
) -> None:
    """Export canonical tables to JSONL (SPEC §2 deliverable)."""
    from nutridb.export import ExportError, export_all, export_jsonl
    from nutridb.paths import paths

    base = paths()
    out_dir = base["build"] / "exports"
    try:
        if table == "all":
            counts = export_all(base["build"] / "canonical", out_dir)
        else:
            path = export_jsonl(table, base["build"] / "canonical", out_dir)
            counts = {table: sum(1 for _ in path.open(encoding="utf-8"))}
    except ExportError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    table_view = rich.table.Table(title="jsonl exports", title_justify="left")
    table_view.add_column("table")
    table_view.add_column("rows", justify="right")
    for name, count in counts.items():
        table_view.add_row(name, f"{count:,}")
    rich.print(table_view)
    typer.echo(f"exports dir: {out_dir}")


@app.command("docs")
def docs(
    target: str = typer.Argument(..., help="dictionary | attributions"),
) -> None:
    """Generate data dictionary / attributions pages (SPEC §2 deliverables)."""
    from nutridb.datadocs import DataDocsError, attributions, data_dictionary
    from nutridb.paths import paths
    from nutridb.sources.registry import load_registry

    base = paths()
    out_dir = base["root"] / "docs" / "generated"
    try:
        if target == "dictionary":
            artifact = base["build"] / "artifacts" / f"nutridb-core-{__version__}.sqlite"
            tables_documented = data_dictionary(artifact, out_dir / "data_dictionary.md")
            typer.echo(f"data dictionary: {tables_documented} tables -> {out_dir}")
        elif target == "attributions":
            registry = load_registry()
            payload = {
                "sources": {
                    source_id: entry.model_dump() if hasattr(entry, "model_dump") else entry
                    for source_id, entry in registry.sources.items()
                }
            }
            count = attributions(payload, out_dir / "ATTRIBUTIONS.md")
            typer.echo(f"attributions: {count} sources -> {out_dir}")
        else:
            raise DataDocsError("unknown target (use dictionary | attributions)")
    except DataDocsError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


@app.command("package")
def package(
    profile: str = typer.Option("core", "--profile", help="core | extended | lite"),
) -> None:
    """Package the canonical dataset into release artefacts (F7, §8)."""
    if profile not in ("core", "lite"):
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
            profile=profile,
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
def build(
    full: bool = typer.Option(
        False, "--full", help="Ignore the stage cache and recompute extract + transform."
    ),
) -> None:
    """Run the full deterministic pipeline (SPEC §16, P10).

    Chains sync -> vocab check -> extract -> transform -> derive -> i18n
    build -> merge -> package -> QA; any stage failure aborts the build (P9).
    Extract and transform are content-addressed in ``build/cache``: an
    unchanged run reuses the previous stage output (byte-identical, P5)
    and only re-runs derive/i18n/merge/package. Source files are verified
    against the registry before extraction.
    """
    from nutridb.cache import CacheError, populate_cache, refresh_from_cache, stage_cache_path
    from nutridb.cache import fingerprint as stage_fingerprint
    from nutridb.derive import DeriveError
    from nutridb.derive import derive as run_derive
    from nutridb.i18n import I18nError
    from nutridb.i18n import build as build_labels
    from nutridb.merge import MergeError
    from nutridb.merge import merge as run_merge
    from nutridb.package import PackageError
    from nutridb.package import package as run_package
    from nutridb.paths import paths
    from nutridb.quality import QualityError, run_quality, write_report
    from nutridb.release import (
        ReleaseError,
        write_attestation,
        write_release_metadata,
    )
    from nutridb.sources.registry import load_registry
    from nutridb.transform import TransformError
    from nutridb.transform import transform as run_transform
    from nutridb.vocab import check_vocabulary

    base = paths()
    registry = load_registry()
    cache_dir = base["build"] / "cache"
    try:
        vocab_report = check_vocabulary(base["root"])
        if vocab_report.errors:
            raise CacheError(f"vocabulary check failed: {vocab_report.errors[:5]}")
        sync_sources(registry)
        extract_reports: dict[str, dict[str, int]] = {}
        for source_id in sorted(registry.sources):
            extractor = _EXTRACTORS.get(source_id)
            if extractor is None:
                raise CacheError(f"registered source {source_id!r} has no extractor")
            source_intermediates = base["build"] / "intermediates" / source_id
            cached: dict[str, int] | None = None
            if not full:
                value = stage_fingerprint(__version__, _extract_inputs(base, source_id))
                cached = (
                    {"cached": 1}
                    if stage_cache_path(cache_dir, "extract", value).is_dir()
                    else None
                )
            if cached is not None:
                refresh_from_cache(cache_dir, source_intermediates, "extract", value)
                extract_reports[source_id] = cached
                continue
            extract_reports[source_id] = extractor(base["cache"] / source_id, source_intermediates)
            if not full:
                populate_cache(cache_dir, "extract", value, source_intermediates)
        transform_report: dict[str, int] = {}
        if not full:
            value = stage_fingerprint(__version__, _transform_inputs(base))
            if stage_cache_path(cache_dir, "transform", value).is_dir():
                refresh_from_cache(cache_dir, base["build"] / "canonical", "transform", value)
                transform_report = {"cached": 1}
        if not transform_report:
            transform_report = run_transform(
                base["build"] / "intermediates",
                base["build"] / "canonical",
                base["root"],
            )
            if not full:
                populate_cache(cache_dir, "transform", value, base["build"] / "canonical")
        derive_report = run_derive(base["build"] / "canonical", base["root"])
        build_labels(base["build"] / "canonical", base["root"])
        merge_report = run_merge(base["build"] / "canonical", base["root"])
        package_info = run_package(
            base["build"] / "canonical",
            base["vocab"],
            base["build"] / "artifacts",
            base["root"],
            profile="core",
        )
        import time

        qa_started = time.perf_counter()
        artifact = base["build"] / "artifacts" / package_info["artifact"]
        findings = run_quality(base["build"] / "canonical", base["vocab"], base["root"], artifact)
        write_report(base["build"] / "qa", findings, artifact, time.perf_counter() - qa_started)
        qa_errors = sum(finding.severity == "error" for finding in findings)
        qa_warnings = sum(finding.severity == "warning" for finding in findings)
        if qa_errors:
            raise PackageError(f"QA blocked release with {qa_errors} error(s)")
        release_info = write_release_metadata(
            artifact,
            base["root"],
            "core",
            base["build"] / "qa" / "metrics.json",
        )
        attestation_info = write_attestation(
            artifact,
            base["root"],
            "core",
            base["build"] / "qa" / "metrics.json",
        )
    except (
        CacheError,
        TransformError,
        DeriveError,
        I18nError,
        MergeError,
        PackageError,
        QualityError,
        ReleaseError,
    ) as exc:
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
    for name, count in derive_report.items():
        table.add_row(f"derive {name}", str(count))
    for name, count in merge_report.items():
        table.add_row(f"merge {name}", str(count))
    table.add_row("artifact", package_info["artifact"])
    table.add_row("size_bytes", f"{package_info['size_bytes']:,}")
    table.add_row("integrity", package_info["integrity"])
    table.add_row("qa_errors", str(qa_errors))
    table.add_row("qa_warnings", str(qa_warnings))
    table.add_row("manifest", release_info["manifest"])
    table.add_row("sbom", release_info["sbom"])
    table.add_row("attestation", attestation_info["attestation"])
    table.add_row("signed", attestation_info["signed"])
    table.add_row("checksums", release_info["checksums"])
    rich.console.Console().print(table)
    typer.echo("build OK")


release_app = typer.Typer(name="release", help="Release verification (ADR-0015).")
app.add_typer(release_app, name="release")


@release_app.command("verify")
def release_verify(
    artifact: Annotated[Path, typer.Argument(help="Path to the release artefact (.sqlite)")],
    public_key: Annotated[
        Path | None,
        typer.Option(
            "--public-key",
            exists=True,
            dir_okay=False,
            help="Ed25519 public key PEM used to verify the attestation signature",
        ),
    ] = None,
) -> None:
    """Verify manifest, SHA256SUMS, SBOM and attestation of a release.

    Recomputes every hash (artifact vs manifest, SBOM root component,
    SHA256SUMS and attestation digests). If the attestation is signed and
    a public key is provided (or ``NUTRIDB_PUBLIC_KEY`` is set), the
    Ed25519 signature is verified; a signed attestation without a key is
    reported as ``unverified``. Any mismatch fails the command (P9).
    """
    from nutridb.release import ReleaseError, verify_release

    key_value = os.environ.get("NUTRIDB_PUBLIC_KEY")
    if key_value is None and public_key is not None:
        key_value = public_key.read_text(encoding="utf-8")
    try:
        report = verify_release(artifact, public_key=key_value)
    except (ReleaseError, OSError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    table = rich.table.Table(title=f"release verify {artifact.name}", title_justify="left")
    table.add_column("item")
    table.add_column("value", justify="right")
    for key, value in report.items():
        table.add_row(key, str(value))
    rich.console.Console().print(table)
    typer.echo("release verify OK")


@app.command("diff")
def diff(
    previous: str = typer.Argument(..., help="previous packaged artifact"),
    current: str = typer.Argument(..., help="current packaged artifact"),
    out: str = typer.Option("", "--out", help="write JSON report to file"),
) -> None:
    """Report value-level differences between two builds (F8)."""
    from nutridb.diff import DiffError, diff_artifacts, write_report

    try:
        report = diff_artifacts(Path(previous), Path(current))
    except DiffError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    table = rich.table.Table(title="artifact diff", title_justify="left")
    table.add_column("metric", justify="right")
    table.add_column("count")
    for metric in (
        "rows_previous",
        "rows_current",
        "added_count",
        "removed_count",
        "changed_count",
    ):
        table.add_row(metric, f"{report[metric]:,}")
    rich.print(table)
    if out:
        write_report(report, Path(out))
        typer.echo(f"report: {out}")


@app.command("serve")
def serve(
    artifact: str = typer.Option("", "--artifact", help="packaged SQLite path"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8600, "--port"),
) -> None:
    """Serve the read-only REST API over a packaged artifact (F9)."""
    from nutridb.paths import paths
    from nutridb.server import serve as run_server

    db_path = (
        Path(artifact)
        if artifact
        else (paths()["build"] / "artifacts" / f"nutridb-core-{__version__}.sqlite")
    )
    if not db_path.is_file():
        typer.secho(f"artifact not found: {db_path}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    run_server(db_path, host, port)


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

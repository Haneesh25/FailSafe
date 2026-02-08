"""CLI commands for Agent Readiness Lab."""

import json
import os
import sys
import time
from pathlib import Path

import click
import httpx
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


def get_api_url() -> str:
    """Get API URL from environment."""
    return os.environ.get("ARLAB_API_URL", "http://localhost:8000")


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Agent Readiness Lab CLI - Test AI agents safely before production."""
    pass


@cli.command()
@click.argument("trace_files", nargs=-1, type=click.Path(exists=True))
@click.option("--api-url", default=None, help="API URL (default: http://localhost:8000)")
def ingest(trace_files: tuple, api_url: str | None):
    """Ingest trace files into the system.

    TRACE_FILES: One or more .jsonl trace files to ingest
    """
    api = api_url or get_api_url()

    if not trace_files:
        console.print("[yellow]No trace files specified.[/yellow]")
        console.print("Usage: arlab ingest examples/traces/*.jsonl")
        return

    with httpx.Client(timeout=30.0) as client:
        for trace_file in trace_files:
            path = Path(trace_file)
            console.print(f"Ingesting [cyan]{path.name}[/cyan]...")

            try:
                with open(path, "rb") as f:
                    response = client.post(
                        f"{api}/ingest_trace",
                        files={"file": (path.name, f, "application/x-ndjson")},
                    )
                    response.raise_for_status()
                    data = response.json()
                    console.print(f"  [green]✓[/green] {data['status']}: {data['session_id']}")
            except Exception as e:
                console.print(f"  [red]✗[/red] Failed: {str(e)}")


@cli.command()
@click.option("--mode", type=click.Choice(["replay", "agent"]), default="replay", help="Evaluation mode")
@click.option("--traces", "-t", multiple=True, help="Trace IDs to evaluate (can specify multiple)")
@click.option("--trace-set", help="Trace set name to evaluate")
@click.option("--runs", default=1, help="Number of runs per trace")
@click.option("--seed", type=int, help="Random seed for mutations")
@click.option("--agent-url", help="External agent URL (for agent mode)")
@click.option("--mutations/--no-mutations", default=False, help="Apply trace mutations")
@click.option("--wait/--no-wait", default=True, help="Wait for completion")
@click.option("--api-url", default=None, help="API URL")
def run(
    mode: str,
    traces: tuple,
    trace_set: str | None,
    runs: int,
    seed: int | None,
    agent_url: str | None,
    mutations: bool,
    wait: bool,
    api_url: str | None,
):
    """Run an evaluation.

    Examples:
        arlab run --mode replay --traces session_1 --traces session_2
        arlab run --mode agent --agent-url http://my-agent:5000
        arlab run --mode replay --mutations --seed 42
    """
    api = api_url or get_api_url()

    request_body = {
        "mode": mode,
        "runs": runs,
        "apply_mutations": mutations,
    }

    if traces:
        request_body["trace_ids"] = list(traces)
    if trace_set:
        request_body["trace_set"] = trace_set
    if seed is not None:
        request_body["seed"] = seed
    if agent_url:
        request_body["agent_url"] = agent_url

    with httpx.Client(timeout=30.0) as client:
        try:
            response = client.post(f"{api}/run_eval", json=request_body)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            console.print(f"[red]Failed to start evaluation: {str(e)}[/red]")
            return

    run_id = data["run_id"]
    console.print(f"[green]Evaluation started:[/green] {run_id}")
    console.print(f"  {data['message']}")

    if not wait:
        console.print(f"\nCheck status with: arlab status {run_id}")
        return

    # Wait for completion
    console.print("\nWaiting for completion...")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Running evaluation...", total=None)

        while True:
            try:
                response = client.get(f"{api}/runs/{run_id}")
                response.raise_for_status()
                status_data = response.json()
            except Exception as e:
                console.print(f"[red]Failed to get status: {str(e)}[/red]")
                break

            status = status_data["status"]
            completed = status_data["completed_sessions"]
            total = status_data["total_sessions"]

            progress.update(task, description=f"Running... {completed}/{total} sessions")

            if status in ("completed", "failed", "cancelled"):
                break

            time.sleep(2)

    # Print results
    console.print()
    if status_data["status"] == "completed":
        console.print("[green]✓ Evaluation completed![/green]")
        _print_metrics(status_data.get("metrics", {}))
    else:
        console.print(f"[red]✗ Evaluation {status_data['status']}[/red]")
        if status_data.get("error_message"):
            console.print(f"  Error: {status_data['error_message']}")

    console.print(f"\nView report: {api}/runs/{run_id}/report")


@cli.command()
@click.argument("run_id")
@click.option("--api-url", default=None, help="API URL")
def status(run_id: str, api_url: str | None):
    """Get status of an evaluation run."""
    api = api_url or get_api_url()

    with httpx.Client(timeout=30.0) as client:
        try:
            response = client.get(f"{api}/runs/{run_id}")
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                console.print(f"[red]Run not found: {run_id}[/red]")
            else:
                console.print(f"[red]Error: {str(e)}[/red]")
            return
        except Exception as e:
            console.print(f"[red]Failed to get status: {str(e)}[/red]")
            return

    console.print(f"[bold]Run:[/bold] {data['run_id']}")
    console.print(f"[bold]Mode:[/bold] {data['mode']}")
    console.print(f"[bold]Status:[/bold] {data['status']}")
    console.print(f"[bold]Progress:[/bold] {data['completed_sessions']}/{data['total_sessions']} sessions")

    if data.get("metrics"):
        console.print()
        _print_metrics(data["metrics"])

    if data.get("error_message"):
        console.print(f"\n[red]Error:[/red] {data['error_message']}")


@cli.command()
@click.argument("run_id")
@click.option("--format", "fmt", type=click.Choice(["html", "json"]), default="html", help="Report format")
@click.option("--output", "-o", type=click.Path(), help="Output file (default: stdout for JSON)")
@click.option("--api-url", default=None, help="API URL")
def report(run_id: str, fmt: str, output: str | None, api_url: str | None):
    """Get report for an evaluation run."""
    api = api_url or get_api_url()

    endpoint = f"{api}/runs/{run_id}/report" if fmt == "html" else f"{api}/runs/{run_id}/json"

    with httpx.Client(timeout=30.0) as client:
        try:
            response = client.get(endpoint)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                console.print(f"[red]Run not found: {run_id}[/red]")
            else:
                console.print(f"[red]Error: {str(e)}[/red]")
            return

    content = response.text if fmt == "html" else json.dumps(response.json(), indent=2)

    if output:
        Path(output).write_text(content)
        console.print(f"[green]Report saved to {output}[/green]")
    else:
        if fmt == "html":
            console.print(f"[yellow]HTML report available at: {endpoint}[/yellow]")
        else:
            print(content)


@cli.command()
@click.option("--api-url", default=None, help="API URL")
def traces(api_url: str | None):
    """List all ingested traces."""
    api = api_url or get_api_url()

    with httpx.Client(timeout=30.0) as client:
        try:
            response = client.get(f"{api}/traces")
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            console.print(f"[red]Failed to list traces: {str(e)}[/red]")
            return

    if not data["traces"]:
        console.print("[yellow]No traces found.[/yellow]")
        console.print("Ingest traces with: arlab ingest examples/traces/*.jsonl")
        return

    table = Table(title="Ingested Traces")
    table.add_column("Session ID", style="cyan")
    table.add_column("Goal")
    table.add_column("Steps", justify="right")
    table.add_column("Tags")

    for trace in data["traces"]:
        table.add_row(
            trace["session_id"][:30],
            trace["goal"][:50] + "..." if len(trace["goal"]) > 50 else trace["goal"],
            str(trace["step_count"]),
            ", ".join(trace["tags"]) if trace["tags"] else "-",
        )

    console.print(table)


@cli.command()
@click.option("--limit", default=20, help="Number of runs to show")
@click.option("--api-url", default=None, help="API URL")
def runs(limit: int, api_url: str | None):
    """List recent evaluation runs."""
    api = api_url or get_api_url()

    with httpx.Client(timeout=30.0) as client:
        try:
            response = client.get(f"{api}/runs", params={"limit": limit})
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            console.print(f"[red]Failed to list runs: {str(e)}[/red]")
            return

    if not data["runs"]:
        console.print("[yellow]No runs found.[/yellow]")
        return

    table = Table(title="Evaluation Runs")
    table.add_column("Run ID", style="cyan")
    table.add_column("Mode")
    table.add_column("Status")
    table.add_column("Sessions", justify="right")
    table.add_column("Success Rate", justify="right")
    table.add_column("Created")

    for run in data["runs"]:
        status_style = {
            "completed": "green",
            "running": "yellow",
            "failed": "red",
            "pending": "dim",
        }.get(run["status"], "")

        success_rate = f"{run['success_rate'] * 100:.1f}%" if run["success_rate"] is not None else "-"

        table.add_row(
            run["run_id"],
            run["mode"],
            f"[{status_style}]{run['status']}[/{status_style}]",
            f"{run['completed_sessions']}/{run['total_sessions']}",
            success_rate,
            run["created_at"][:19],
        )

    console.print(table)


def _print_metrics(metrics: dict):
    """Print metrics in a nice format."""
    table = Table(title="Metrics", show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    if "success_rate" in metrics and metrics["success_rate"] is not None:
        table.add_row("Success Rate", f"{metrics['success_rate'] * 100:.1f}%")
    if "median_time_to_complete_ms" in metrics and metrics["median_time_to_complete_ms"] is not None:
        table.add_row("Median Time", f"{metrics['median_time_to_complete_ms'] / 1000:.2f}s")
    if "error_recovery_rate" in metrics and metrics["error_recovery_rate"] is not None:
        table.add_row("Error Recovery Rate", f"{metrics['error_recovery_rate'] * 100:.1f}%")
    if "harmful_action_blocks" in metrics:
        table.add_row("Blocked Actions", str(metrics["harmful_action_blocks"]))
    if "tool_call_count" in metrics:
        table.add_row("Total Tool Calls", str(metrics["tool_call_count"]))
    if "abandonment_rate" in metrics and metrics["abandonment_rate"] is not None:
        table.add_row("Abandonment Rate", f"{metrics['abandonment_rate'] * 100:.1f}%")

    console.print(table)


if __name__ == "__main__":
    cli()

"""CLI entry point: `failsafe dashboard`, etc."""

from __future__ import annotations

import click


@click.group()
def main():
    """FailSafe — contract testing for multi-agent AI systems."""
    pass


@main.command()
@click.option("--port", default=8765, help="Dashboard port")
@click.option("--host", default="0.0.0.0", help="Dashboard host")
def dashboard(port: int, host: str):
    """Launch the FailSafe dashboard."""
    import uvicorn

    from failsafe.core.engine import FailSafe
    from failsafe.dashboard.server import create_app

    fs = FailSafe()
    app = create_app(fs)
    click.echo(f"Starting FailSafe dashboard on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


@main.command()
def version():
    """Show FailSafe version."""
    click.echo("failsafe-ai 0.1.0")


if __name__ == "__main__":
    main()

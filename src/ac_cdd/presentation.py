import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from .services.file_ops import PatchResult


class ConsolePresenter:
    """
    Handles presentation of file operations to the console using rich.
    """
    def __init__(self) -> None:
        self.console = Console()

    def print_patch_results(self, results: list[PatchResult]) -> None:
        """
        Prints the results of file patches.
        """
        for result in results:
            if result.success:
                style = "green" if "patched" in result.message else "blue"
                self.console.print(
                    Panel(
                        f"{result.message}: [bold]{result.file_path}[/bold] ({result.operation})",
                        style=style,
                    )
                )
                if result.diff_text:
                    syntax = Syntax(result.diff_text, "diff", theme="monokai", line_numbers=True)
                    self.console.print(syntax)
            else:
                self.console.print(
                    Panel(
                        f"Failed: {result.message} for [bold]{result.file_path}[/bold]", style="red"
                    )
                )

    def review_and_confirm(self, results: list[PatchResult]) -> bool:
        """
        Present previews (if dry_run was used effectively to generate diffs without applying)
        and ask for confirmation.
        """
        self.print_patch_results(results)

        # If any result was not successful (failed to patch), we might want to warn
        if any(not r.success for r in results):
            self.console.print("[yellow]Warning: Some patches failed.[/yellow]")

        if not results:
            self.console.print("No changes to review.")
            return True

        return typer.confirm("Apply these changes?", default=True)

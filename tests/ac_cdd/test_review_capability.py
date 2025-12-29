import argparse
import asyncio
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from ac_cdd_core.config import settings
from ac_cdd_core.services.git_ops import GitManager
from ac_cdd_core.services.aider_client import AiderClient
from ac_cdd_core.services.jules_client import JulesClient
from ac_cdd_core.sandbox import SandboxRunner

console = Console()

async def main():
    parser = argparse.ArgumentParser(description="Evaluate Code Review Capability")
    parser.add_argument("--pr", required=True, help="Pull Request URL")
    parser.add_argument("--session", required=True, help="Jules Session ID")
    args = parser.parse_args()
    
    git = GitManager()
    aider = AiderClient()
    jules = JulesClient()
    runner = SandboxRunner()
    
    console.print(Panel(f"PR: {args.pr}\nSession: {args.session}", title="Review Capability Test", style="bold blue"))
    
    original_branch = None
    
    try:
        # 1. Checkout PR
        with console.status("[bold green]Checking out PR..."):
            try:
                original_branch = await git.get_current_branch()
            except:
                original_branch = "main"
                
            await git.checkout_pr(args.pr)
            current_branch = await git.get_current_branch()
            console.print(f"Checked out: [bold]{current_branch}[/bold]")
        
        # 2. Identify Changed Files
        with console.status("[bold green]Identifying changes..."):
            changed_files = await git.get_changed_files("main")
            
        console.print(f"Changed Files ({len(changed_files)}):")
        for f in changed_files:
            console.print(f" - {f}")
            
        files_to_audit = []
        for f in changed_files:
            if f.endswith(".py") or f in ["ac_cdd_config.py", "pyproject.toml"]:
                if Path(f).exists():
                    files_to_audit.append(f)
                    
        arch_doc = Path(settings.paths.documents_dir) / "SYSTEM_ARCHITECTURE.md"
        if arch_doc.exists():
            console.print(f" - {arch_doc} (Context)")
            files_to_audit.append(str(arch_doc))
            
        if not files_to_audit:
            console.print("[yellow]No relevant files to audit. Exiting.[/yellow]")
            return

        # 3. Conduct Review
        with console.status("[bold green]Running Auditor (Aider) in Sandbox..."):
            instruction = Path(settings.paths.templates / "AUDITOR_INSTRUCTION.md").read_text() if (Path(settings.paths.templates) / "AUDITOR_INSTRUCTION.md").exists() else "Review strictly."
            instruction += "\n\n(Single Review Mode: Provide comprehensive feedback.)"
            
            # Using AiderClient
            raw_output = await aider.run_audit(
                files=files_to_audit,
                instruction=instruction,
                runner=runner
            )
            
            # PARSE OUTPUT using Core Logic
            clean_report = aider.parse_audit_report(raw_output)
        
        console.print(Panel(clean_report, title="Audit Report", subtitle="Feedback to Jules", style="red"))
        
        # 4. Send API Feedback
        with console.status(f"[bold green]Sending Feedback to Cycle {args.session}..."):
            session_path = args.session
            if not session_path.startswith("sessions/"):
                session_path = f"sessions/{session_path}"
                
            await jules._send_message(session_path, clean_report)
            
        console.print("[bold green]Feedback sent successfully![/bold green]")

    except Exception as e:
        console.print_exception()
    finally:
        # Cleanup
        try:
            if original_branch and original_branch != await git.get_current_branch():
                console.print(f"Restoring branch {original_branch}...")
                await git.runner.run_command(["git", "checkout", original_branch], check=False)
        except Exception:
            pass
        await runner.close()

if __name__ == "__main__":
    asyncio.run(main())

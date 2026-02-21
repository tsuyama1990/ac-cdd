import re

# 1. Add resume_session to WorkflowService
workflow_path = "dev_src/ac_cdd_core/services/workflow.py"
with open(workflow_path) as f:
    wf_text = f.read()

resume_code = """    def resume_session(self, feature_branch: str, integration_branch: str | None, cycles: int) -> None:
        \"\"\"Resume session with existing branches.\"\"\"
        from datetime import UTC, datetime
        from ac_cdd_core.domain_models import CycleManifest, ProjectManifest
        from ac_cdd_core.state_manager import StateManager

        session_id = f"resume-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"

        if not integration_branch:
            parts = feature_branch.split("-")
            if len(parts) >= 3:
                timestamp = "-".join(parts[-2:])
                integration_branch = f"dev/architect-cycle-00-{timestamp}/integration"
            else:
                integration_branch = f"dev/{feature_branch}/integration"

        console.print("[bold cyan]Resuming session with existing branches:[/bold cyan]")
        console.print(f"  Feature branch: [green]{feature_branch}[/green]")
        console.print(f"  Integration branch: [green]{integration_branch}[/green]")
        console.print(f"  Cycles: [green]{cycles}[/green]")

        mgr = StateManager()
        manifest = ProjectManifest(
            project_session_id=session_id,
            feature_branch=feature_branch,
            integration_branch=integration_branch,
            cycles=[CycleManifest(id=f"{i:02}", status="planned") for i in range(1, cycles + 1)],
        )
        mgr.save_manifest(manifest)

        console.print("\\n[bold green]✅ Session resumed![/bold green]")
        console.print(f"Session ID: [cyan]{session_id}[/cyan]")
        console.print("\\nYou can now run:")
        console.print("  [bold]ac-cdd run-cycle --id 01[/bold]")
        console.print("  [bold]ac-cdd run-cycle --id all[/bold]")

"""

# Insert right after `def __init__(self) -> None:` method ends
# We'll just replace `    def run_gen_cycles` with the new method + `    def run_gen_cycles`
wf_text = wf_text.replace("    def run_gen_cycles(", resume_code + "    def run_gen_cycles(")

with open(workflow_path, "w") as f:
    f.write(wf_text)

# 2. Refactor cli.py
cli_path = "dev_src/ac_cdd_core/cli.py"
with open(cli_path) as f:
    cli_text = f.read()

# Delete _WorkflowServiceHolder
holder_pattern = r"class _WorkflowServiceHolder:.*?return cls\._instance\n\n\n"
cli_text = re.sub(holder_pattern, "", cli_text, flags=re.DOTALL)

# Delete _is_docker_environment
docker_pattern = r"def _is_docker_environment\(\) -> bool:.*?return os\.environ\.get\(\"DOCKER_CONTAINER\"\) == \"true\"\n\n\n"
cli_text = re.sub(docker_pattern, "", cli_text, flags=re.DOTALL)

# Find and Replace Holder usages
cli_text = cli_text.replace("_WorkflowServiceHolder.get()", "WorkflowService()")

# Replace _resume_session block and delegate to WorkflowService
resume_pattern = r"def _resume_session\(.*?console\.print\(\"  \[bold\]ac-cdd run-cycle --id all\[/bold\]\"\)\n\n\n"
cli_text = re.sub(resume_pattern, "", cli_text, flags=re.DOTALL)

# Update the call in `@app.command() def resume_session`
cli_text = cli_text.replace("    _resume_session(feature_branch, integration_branch, cycles)", "    WorkflowService().resume_session(feature_branch, integration_branch, cycles)")


with open(cli_path, "w") as f:
    f.write(cli_text)

print("Done")

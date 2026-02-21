from pathlib import Path

from ac_cdd_core.config import settings
from ac_cdd_core.services.git_ops import GitManager
from ac_cdd_core.state_manager import StateManager
from ac_cdd_core.utils import logger


class JulesContextBuilder:
    def __init__(self, git: GitManager) -> None:
        self.git = git

    def construct_run_prompt(
        self,
        prompt: str,
        files: list[str] | None,
        target_files: list[str] | None,
        context_files: list[str] | None,
    ) -> str:
        full_prompt = prompt
        if target_files or context_files:
            full_prompt += "\n\n" + "#" * 20 + "\nFILE CONTEXT:\n"
            if context_files:
                full_prompt += "\nREAD-ONLY CONTEXT (Do not edit):\n" + "\n".join(context_files)
            if target_files:
                full_prompt += "\n\nTARGET FILES (To be implemented/edited):\n" + "\n".join(
                    target_files
                )
        elif files:
            file_list_str = "\n".join(files)
            full_prompt += f"\n\nPlease focus on the following files:\n{file_list_str}"
        return full_prompt

    def load_cycle_docs(self, current_cycle: str, context_parts: list[str]) -> None:
        """Load SPEC.md and UAT.md for the current cycle."""
        spec_path = Path(f"dev_documents/system_prompts/CYCLE{current_cycle}/SPEC.md")
        if spec_path.exists():
            spec_content = spec_path.read_text(encoding="utf-8")
            context_parts.append(f"\n## Cycle Specification\n```markdown\n{spec_content}\n```\n")

        uat_path = Path(f"dev_documents/system_prompts/CYCLE{current_cycle}/UAT.md")
        if uat_path.exists():
            uat_content = uat_path.read_text(encoding="utf-8")
            context_parts.append(f"\n## User Acceptance Tests\n```markdown\n{uat_content}\n```\n")

    async def load_changed_files(self, context_parts: list[str]) -> None:
        """Load content of changed files in the current branch."""
        changed_files = await self.git.get_changed_files()
        if not changed_files:
            return

        context_parts.append(f"\n## Changed Files ({len(changed_files)} files)\n")

        max_files = 10  # Prevent context overflow
        max_file_size = 5000  # chars per file

        for filepath in changed_files[:max_files]:
            try:
                file_path = Path(filepath)
                if file_path.exists() and file_path.suffix in [
                    ".py",
                    ".md",
                    ".toml",
                    ".json",
                    ".yaml",
                    ".yml",
                ]:
                    content = file_path.read_text(encoding="utf-8")
                    if len(content) > max_file_size:
                        content = content[:max_file_size] + "\n... (truncated)"
                    context_parts.append(
                        f"\n### {filepath}\n```{file_path.suffix[1:]}\n{content}\n```\n"
                    )
            except Exception as e:
                logger.debug(f"Could not read {filepath}: {e}")
                continue

    def load_architecture_summary(self, context_parts: list[str]) -> None:
        """Load system architecture summary."""
        arch_path = Path("dev_documents/system_prompts/SYSTEM_ARCHITECTURE.md")
        if not arch_path.exists():
            return

        arch_content = arch_path.read_text(encoding="utf-8")
        summary_end = arch_content.find("\n## ")
        if summary_end > 0:
            arch_summary = arch_content[:summary_end]
            context_parts.append(
                f"\n## System Architecture (Summary)\n```markdown\n{arch_summary}\n```\n"
            )

    async def build_question_context(self, question: str) -> str:
        """
        Builds comprehensive context for answering Jules' questions.
        Includes: current cycle SPEC, changed files, and their contents.
        """
        context_parts = [f"# Jules' Question\n{question}\n"]

        try:
            # 1. Get current cycle information from session manifest
            mgr = StateManager()
            manifest = mgr.load_manifest()

            # Find current active cycle (in_progress) or fallback to last cycle if needed
            current_cycle_id: str | None = None
            if manifest:
                for cycle in manifest.cycles:
                    if cycle.status == "in_progress":
                        current_cycle_id = cycle.id
                        break

            if current_cycle_id:
                context_parts.append(f"\n# Current Cycle: {current_cycle_id}\n")
                self.load_cycle_docs(current_cycle_id, context_parts)

            await self.load_changed_files(context_parts)
            self.load_architecture_summary(context_parts)

        except Exception as e:
            logger.warning(f"Failed to build full context for Jules question: {e}")
            return question

        full_context = "\n".join(context_parts)
        instruction = settings.get_prompt_content(
            "MANAGER_INQUIRY_PROMPT.md",
            default=(
                "**Instructions for Answering Jules' Question**:\n"
                "Focus on ROOT CAUSE ANALYSIS. Diagnose the underlying cause, "
                "guide investigation, and provide targeted solutions."
            ),
        )
        full_context += f"\n\n---\n{instruction}"

        return full_context

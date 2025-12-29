import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parents[2]
sys.path.append(str(project_root))

from dev_src.ac_cdd_core.config import settings  # noqa: E402
from dev_src.ac_cdd_core.services.git_ops import GitManager  # noqa: E402
from dev_src.ac_cdd_core.services.jules_client import JulesClient  # noqa: E402
from dev_src.ac_cdd_core.services.llm_reviewer import LLMReviewer  # noqa: E402


async def main():
    print("=== LLM Reviewer Audit Debug (Session 1461081734443671409) ===")

    session_id = "1461081734443671409"
    jules_client = JulesClient()
    git = GitManager()
    reviewer = LLMReviewer()

    # 1. Get Session Details & PR URL
    print(f"Fetching session info for {session_id}...")
    try:
        session_path = f"sessions/{session_id}"
        session_data = jules_client.api_client._request("GET", session_path)

        pr_url = None
        if "outputs" in session_data:
            for output in session_data["outputs"]:
                if "pullRequest" in output:
                    pr_url = output["pullRequest"].get("url")
                    break

        if not pr_url:
            print("No PR URL found in session outputs.")
        else:
            print(f"Found PR URL: {pr_url}")

            # 2. Checkout PR
            try:
                # SKIP Clean State to avoid stashing this script itself!
                # await git.ensure_clean_state()
                await git.checkout_pr(pr_url)
            except Exception as e:
                print(f"Error checking out PR (proceeding anyway if possible): {e}")

    except Exception as e:
        print(f"Failed to fetch session: {e}")

    # 3. Identify Files to Audit
    print("Identifying changed files...")
    files_to_audit = []
    try:
        # Get changed files vs main
        changed = await git.get_changed_files(base_branch="main")
        files_to_audit.extend(changed)
    except Exception as e:
        print(f"Failed to get changed files: {e}")
        files_to_audit.append("ac_cdd_config.py")

    # Filter for py/md/toml only
    extensions = [".py", ".toml", ".md"]
    files_to_audit = [f for f in files_to_audit if any(f.endswith(ext) for ext in extensions)]
    files_to_audit = sorted(list(set(files_to_audit)))

    if not files_to_audit:
        print("No relevant changed files found. Auditing 'ac_cdd_config.py' as smoke test.")
        files_to_audit = ["ac_cdd_config.py"]

    print(f"Auditing {len(files_to_audit)} files: {files_to_audit}")

    # 4. Read File Content
    files_content = {}
    cwd = Path.cwd()
    for f_path in files_to_audit:
        p = cwd / f_path
        if p.exists():
            files_content[f_path] = p.read_text(encoding="utf-8")
        else:
            print(f"File not found: {f_path}")

    # 5. Run Review
    instruction = (
        "Perform a strict code review. Check for security issues, "
        "hardcoded credentials, and architectural violations."
    )

    # Use FAST_MODEL for reading
    model = settings.reviewer.fast_model
    print(f"Sending to LLM ({model})...")

    try:
        result = await reviewer.review_code(files_content, instruction, model)
        print("\n=== Audit Result ===\n")
        print(result)
        print("\n=== End Result ===")
    except Exception as e:
        print(f"Review failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())

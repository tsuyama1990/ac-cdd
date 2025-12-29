import asyncio
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = (
    Path(__file__).resolve().parents[1]
    if "scripts" in str(Path(__file__))
    else Path(__file__).resolve().parent
)
sys.path.append(str(project_root))

try:
    from dev_src.ac_cdd_core.services.aider_client import AiderClient

    from dev_src.ac_cdd_core.sandbox import SandboxRunner
except ImportError:
    sys.path.append(str(project_root / "dev_src"))
    from ac_cdd_core.sandbox import SandboxRunner
    from ac_cdd_core.services.aider_client import AiderClient


async def main():
    print("=== Aider Audit Simulation (SANDBOX MODE) Start ===")

    # 1. クライアントの初期化
    client = AiderClient()

    # 2. SandboxRunnerの初期化 (ここでE2Bに接続・環境構築が行われます)
    print("Initializing Sandbox... (This may take a moment)")
    runner = SandboxRunner()

    # 3. 監査対象ファイルの収集
    src_dir = Path("dev_src")
    tests_dir = Path("tests")

    files_to_audit = ["ac_cdd_config.py"]

    if src_dir.exists():
        files_to_audit.extend([str(p) for p in src_dir.rglob("*.py")])
    if tests_dir.exists():
        files_to_audit.extend([str(p) for p in tests_dir.rglob("*.py")])

    # 重複排除とソート
    files_to_audit = sorted(list(set(files_to_audit)))

    # === 変更点: 最初の10ファイルに限定 ===
    files_to_audit = files_to_audit[:3]

    print("Target Files (Limited to 3):")
    for f in files_to_audit:
        print(f" - {f}")

    # 4. 指示書の読み込み
    template_path = Path("dev_documents/templates/AUDITOR_INSTRUCTION.md")
    if not template_path.exists():
        print(f"Error: Instruction file not found at {template_path}")
        # フォールバック用のダミー指示
        instruction = "Review the code strictly for architecture and robustness."
    else:
        instruction = template_path.read_text(encoding="utf-8")

    instruction += "\n\n(Debug Simulation in Sandbox: Iteration 1)"

    print("\n--- Sending Request to Remote Aider (Fast Model) ---")
    print("Waiting for response from Sandbox...")

    try:
        # 5. 監査実行 (SandboxRunnerを渡すことでリモート実行になります)
        result = await client.run_audit(
            files=files_to_audit, instruction=instruction, runner=runner
        )

        print("\n=== Remote Aider Response Output ===\n")
        print(result)
        print("\n=== End of Response ===")

    except Exception as e:
        print(f"\nError during audit execution: {e}")
        import traceback

        traceback.print_exc()

    finally:
        # Sandboxのクリーンアップ（接続切断）
        if runner:
            print("\nClosing Sandbox connection...")
            await runner.close()


if __name__ == "__main__":
    asyncio.run(main())

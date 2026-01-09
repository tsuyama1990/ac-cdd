import os
import sys
import unittest
from typer.testing import CliRunner

# Ensure the project root is in sys.path
sys.path.insert(0, os.path.abspath("."))

# Set dummy keys before importing cli which might import settings that validate keys
os.environ["ANTHROPIC_API_KEY"] = "dummy"
os.environ["GEMINI_API_KEY"] = "dummy"
os.environ["OPENROUTER_API_KEY"] = "dummy"
os.environ["JULES_API_KEY"] = "dummy"
os.environ["E2B_API_KEY"] = "dummy"
os.environ["AC_CDD_AUDITOR_MODEL"] = "openai:gpt-4o"
os.environ["AC_CDD_QA_ANALYST_MODEL"] = "openai:gpt-4o"
os.environ["AC_CDD_REVIEWER__SMART_MODEL"] = "openai:gpt-4o"
os.environ["AC_CDD_REVIEWER__FAST_MODEL"] = "openai:gpt-3.5-turbo"

# Attempt to import the app. If this fails, the test script will crash,
# which is a valid result for an operation test (failure).
try:
    from dev_src.ac_cdd_core.cli import app
except ImportError:
    # Fallback for when running not via uv/editable install
    sys.path.append(os.path.join(os.getcwd(), 'dev_src'))
    from dev_src.ac_cdd_core.cli import app

class TestDosa(unittest.TestCase):
    """
    Operation Test (Dosa Test) for AC-CDD CLI.
    Verifies that the main entry point is operational.
    """
    def setUp(self):
        self.runner = CliRunner()

    def test_cli_help(self):
        """Test that the CLI entry point responds to --help."""
        result = self.runner.invoke(app, ["--help"])

        # Verify exit code
        self.assertEqual(result.exit_code, 0, f"CLI --help failed with: {result.stdout}")

        # Verify output contains expected description
        self.assertIn("AC-CDD", result.stdout)
        self.assertIn("AI-Native Cycle-Based Contract-Driven Development", result.stdout)

    def test_list_actions(self):
        """Test list-actions command runs (it should run even without session)."""
        result = self.runner.invoke(app, ["list-actions"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Recommended Actions", result.stdout)

if __name__ == "__main__":
    print("Running dosa_test.py (Operation Test)...")
    unittest.main()

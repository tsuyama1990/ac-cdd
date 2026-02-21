import re

file_path = "dev_src/ac_cdd_core/services/jules_client.py"
with open(file_path) as f:
    text = f.read()

# Replace Imports
new_imports = """
from .jules.context_builder import JulesContextBuilder
from .jules.git_context import JulesGitContext, JulesSessionError
from .jules.inquiry_handler import JulesInquiryHandler
"""
text = text.replace("from .jules.api import JulesApiClient\n", "from .jules.api import JulesApiClient\n" + new_imports)

# Replace __init__ to include these
init_pattern = r"def __init__\(self\) -> None:.*?self\.api_client = JulesApiClient\(api_key=api_key_to_use\)"
new_init = """def __init__(self) -> None:
        self.project_id = settings.GCP_PROJECT_ID
        self.base_url = "https://jules.googleapis.com/v1alpha"
        self.timeout = settings.jules.timeout_seconds
        self.poll_interval = settings.jules.polling_interval_seconds
        self.console = Console()
        self.git = GitManager()

        try:
            self.credentials, self.project_id_from_auth = google.auth.default()  # type: ignore[no-untyped-call]
            if not self.project_id:
                self.project_id = self.project_id_from_auth
        except Exception as e:
            logger.warning(
                f"Could not load Google Credentials: {e}. Falling back to API Key if available."
            )
            self.credentials = None

        self.manager_agent = get_manager_agent()

        # Import PlanAuditor for plan approval (separate from manager_agent for questions)
        from ac_cdd_core.services.plan_auditor import PlanAuditor

        self.plan_auditor = PlanAuditor()

        api_key_to_use = settings.JULES_API_KEY
        if not api_key_to_use and self.credentials:
            api_key_to_use = self.credentials.token

        self.api_client = JulesApiClient(api_key=api_key_to_use)
        self.context_builder = JulesContextBuilder(self.git)
        self.git_context = JulesGitContext(self.git)
        self.inquiry_handler = JulesInquiryHandler(
            manager_agent=self.manager_agent,
            context_builder=self.context_builder,
            client_ref=self
        )"""

text = re.sub(init_pattern, new_init, text, flags=re.DOTALL)

# Delete extracted methods
methods_to_delete = [
    r"    async def _prepare_git_context\(.*?(?=    def |    async def )",
    r"    def _raise_jules_session_error\(.*?(?=    def |    async def )",
    r"    def _construct_run_prompt\(.*?(?=    async def |    def )",
    r"    async def _check_for_inquiry\(.*?(?=    def |    async def )",
    r"    def _extract_activity_message\(.*?(?=    async def |    def )",
    r"    def _load_cycle_docs\(.*?(?=    async def |    def )",
    r"    async def _load_changed_files\(.*?(?=    def |    async def )",
    r"    def _load_architecture_summary\(.*?(?=    async def |    def )",
    r"    async def _build_question_context\(.*?(?=    async def |    def )",
    r"    async def _fetch_pending_plan\(.*?(?=    async def |    def )",
    r"    async def _build_plan_review_context\(.*?(?=    async def |    def )",
    r"    async def _handle_plan_approval\(.*?(?=    async def |    def )",
    r"    async def _process_inquiries\(.*?(?=    async def |    def )",
]

for pattern in methods_to_delete:
    text = re.sub(pattern, "", text, flags=re.DOTALL)

# Find and replace references in run_session
text = text.replace("self._prepare_git_context(", "self.git_context.prepare_git_context(")
text = text.replace("self._construct_run_prompt(", "self.context_builder.construct_run_prompt(")
text = text.replace("self._process_inquiries(", "self.inquiry_handler.process_inquiries(")
text = text.replace("self._extract_activity_message(", "self.inquiry_handler.extract_activity_message(")

with open(file_path, "w") as f:
    f.write(text)

print("Done")

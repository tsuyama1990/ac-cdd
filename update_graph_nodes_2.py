import re

with open("dev_src/ac_cdd_core/graph_nodes.py", "r") as f:
    content = f.read()

replacement = """    async def committee_manager_node(self, state: CycleState) -> dict[str, Any]:
        from ac_cdd_core.services.committee_usecase import CommitteeUseCase
        usecase = CommitteeUseCase()
        return dict(await usecase.execute(state))

    async def uat_evaluate_node(self, state: CycleState) -> dict[str, Any]:
        from ac_cdd_core.services.uat_usecase import UatUseCase
        usecase = UatUseCase(self.git)
        return dict(await usecase.execute(state))

    def check_coder_outcome(self, state: CycleState) -> str:
        from ac_cdd_core.enums import FlowStatus
        if state.get("final_fix", False):
            return str(FlowStatus.COMPLETED)

        status = state.get("status")
        if status == FlowStatus.CODER_RETRY:
            return str(FlowStatus.CODER_RETRY)
        if status == FlowStatus.READY_FOR_AUDIT:
            return str(FlowStatus.READY_FOR_AUDIT)
        if status in {FlowStatus.FAILED, FlowStatus.ARCHITECT_FAILED}:
            return str(FlowStatus.FAILED)
        return str(FlowStatus.COMPLETED)

    def check_audit_outcome(self, _state: CycleState) -> str:
        return "rejected_retry"

    def route_committee(self, state: CycleState) -> str:
        from ac_cdd_core.enums import FlowStatus
        status = state.get("status")
        if status == FlowStatus.NEXT_AUDITOR:
            return "auditor"
        if status == FlowStatus.CYCLE_APPROVED:
            return "uat_evaluate"
        if status == FlowStatus.RETRY_FIX:
            return "coder_session"
        if status == FlowStatus.WAIT_FOR_JULES_COMPLETION:
            return "coder_session"
        return "failed"

    def route_uat(self, state: CycleState) -> str:
        from ac_cdd_core.enums import FlowStatus
        status = state.get("status")
        if status == FlowStatus.START_REFACTOR:
            return "coder_session"
        if status == FlowStatus.COMPLETED:
            return "end"
        return "end"

    async def qa_session_node(self, state: CycleState) -> dict[str, Any]:
        from ac_cdd_core.services.qa_usecase import QaUseCase
        usecase = QaUseCase(self.jules, self.git, self.llm_reviewer)
        return dict(await usecase.execute_qa_session(state))

    async def qa_auditor_node(self, state: CycleState) -> dict[str, Any]:
        from ac_cdd_core.services.qa_usecase import QaUseCase
        usecase = QaUseCase(self.jules, self.git, self.llm_reviewer)
        return dict(await usecase.execute_qa_audit(state))

    def route_qa(self, state: CycleState) -> str:
        from ac_cdd_core.enums import FlowStatus
        status = state.get("status")
        if status == FlowStatus.APPROVED:
            return "end"
        if status == FlowStatus.REJECTED:
            return "retry_fix"
        return "failed"
"""

# Replace everything from `    async def committee_manager_node...` to the end of the file
pattern = r'    async def committee_manager_node\(self, state: CycleState\) -> dict\[str, Any\]:.*'
content = re.sub(pattern, replacement, content, flags=re.DOTALL)

with open("dev_src/ac_cdd_core/graph_nodes.py", "w") as f:
    f.write(content)

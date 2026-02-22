import re

with open("dev_src/ac_cdd_core/graph_nodes.py", "r") as f:
    content = f.read()

# Replace _read_files
content = re.sub(r'    async def _read_files\(self, file_paths: list\[str\]\) -> dict\[str, str\]:.*?return result\n', '', content, flags=re.DOTALL)

# Replace _run_static_analysis
content = re.sub(r'    async def _run_static_analysis\(self, target_files: list\[str\] \| None = None\) -> tuple\[bool, str\]:.*?return success, "\\n\\n"\.join\(output\)\n', '', content, flags=re.DOTALL)

# Replace coder_session_node
coder_replacement = """    async def coder_session_node(self, state: CycleState) -> dict[str, Any]:
        from ac_cdd_core.services.coder_usecase import CoderUseCase
        usecase = CoderUseCase(self.jules)
        return await usecase.execute(state)
"""
content = re.sub(r'    async def coder_session_node\(self, state: CycleState\) -> dict\[str, Any\]:.*?(?=    async def auditor_node)', coder_replacement + "\n", content, flags=re.DOTALL)

# Replace auditor_node
auditor_replacement = """    async def auditor_node(self, state: CycleState) -> dict[str, Any]:
        from ac_cdd_core.services.auditor_usecase import AuditorUseCase
        usecase = AuditorUseCase(self.jules, self.git, self.llm_reviewer)
        return await usecase.execute(state)
"""
content = re.sub(r'    async def auditor_node\(self, state: CycleState\) -> dict\[str, Any\]:.*?(?=    async def committee_manager_node)', auditor_replacement + "\n", content, flags=re.DOTALL)

with open("dev_src/ac_cdd_core/graph_nodes.py", "w") as f:
    f.write(content)

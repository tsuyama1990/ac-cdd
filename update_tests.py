
def update_test_committee_logic():
    path = "tests/ac_cdd/unit/test_committee_logic.py"
    with open(path) as f:
        content = f.read()

    content = content.replace('"ac_cdd_core.graph_nodes.settings"', '"ac_cdd_core.services.committee_usecase.settings"')

    with open(path, "w") as f:
        f.write(content)

def update_test_audit_polling():
    path = "tests/ac_cdd/unit/test_audit_polling.py"
    with open(path) as f:
        content = f.read()

    content = content.replace('state = {', 'state = CycleState(')
    content = content.replace('    "cycle_id": "99",\n', '    cycle_id="99",\n')
    content = content.replace('    "feature_branch": "dev/int-test",\n', '    feature_branch="dev/int-test",\n')
    content = content.replace('    "last_audited_commit": None\n', '    last_audited_commit=None\n')
    content = content.replace('}', ')')

    # Also fix patching for AuditorUseCase instead of graph_nodes
    content = content.replace('"ac_cdd_core.graph_nodes.GitManager"', '"ac_cdd_core.services.auditor_usecase.GitManager"')
    content = content.replace('"ac_cdd_core.graph_nodes.LLMReviewer"', '"ac_cdd_core.services.auditor_usecase.LLMReviewer"')
    content = content.replace('ac_cdd_core.graph_nodes.settings', 'ac_cdd_core.services.auditor_usecase.settings')

    with open(path, "w") as f:
        f.write(content)

update_test_committee_logic()
# update_test_audit_polling()  # Needs more careful replacement possibly. Let's do it via sed/manual script

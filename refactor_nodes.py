import re

with open("dev_src/ac_cdd_core/jules_session_nodes.py") as f:
    text = f.read()

# Add _get_diff method to class
diff_method = """
    def _get_diff(self, original: JulesSessionState, current: JulesSessionState) -> dict[str, Any]:
        \"\"\"Compute dictionary of changed fields for LangGraph checkpointer.\"\"\"
        updates = {}
        for field in current.model_fields:
            old_val = getattr(original, field)
            new_val = getattr(current, field)
            if old_val != new_val:
                updates[field] = new_val
        return updates
"""

# Insert _get_diff after __init__
init_end = text.find("    async def monitor_session")
text = text[:init_end] + diff_method + "\n" + text[init_end:]

# Replace signature of state-modifying nodes and add copy logic
def replace_node(name):
    global text

    # 1. Update signature
    old_sig = f"async def {name}(self, state: JulesSessionState) -> JulesSessionState"
    new_sig = f"async def {name}(self, _state_in: JulesSessionState) -> dict[str, Any]"

    # If the signature is split on multiple lines, regex might be needed.
    # Searching for signature
    pattern = r"async def " + name + r"\(self, state: JulesSessionState\).*?:"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        print(f"Could not find {name}")
        return

    sig = match.group(0)
    new_sig_full = sig.replace("state: JulesSessionState", "_state_in: JulesSessionState").replace("-> JulesSessionState", "-> dict[str, Any]")

    # We add state_copy logic right after the docstring
    # Find the end of docstring
    fn_body_start = text.find(":", match.start()) + 1

    # Find next line
    next_newline = text.find("\n", fn_body_start)
    next_line_start = next_newline + 1

    # Find docstring
    docstring_match = re.search(r'^\s*"""[\s\S]*?"""', text[next_line_start:])
    if docstring_match:
        insert_pos = next_line_start + docstring_match.end()
    else:
        insert_pos = next_line_start

    # Replace return state with return self._get_diff
    # We only want to replace returns inside this function.
    # We find the end of the function by looking for the next '    async def ' or '    def '
    next_def = re.search(r'\n    (?:async )?def ', text[insert_pos:])
    fn_end = insert_pos + next_def.start() if next_def else len(text)

    fn_text = text[insert_pos:fn_end]
    fn_text = re.sub(r'return state', r'return self._get_diff(_state_in, state)', fn_text)
    # Also distress_state in validate_completion
    if name == "validate_completion":
        fn_text = re.sub(r'return distress_state', r'return self._get_diff(_state_in, distress_state)', fn_text)

    # Reassemble
    text = text[:match.start()] + new_sig_full + text[fn_body_start:insert_pos] + "\n        state = _state_in.model_copy(deep=True)\n" + fn_text + text[fn_end:]

nodes = ["monitor_session", "answer_inquiry", "validate_completion", "check_pr", "request_pr_creation", "wait_for_pr"]
for node in nodes:
    replace_node(node)

with open("dev_src/ac_cdd_core/jules_session_nodes.py", "w") as f:
    f.write(text)
print("Done")

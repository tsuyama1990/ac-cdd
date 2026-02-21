import re

file_path = "dev_src/ac_cdd_core/jules_session_nodes.py"
with open(file_path, "r") as f:
    text = f.read()

diff_method = """
    def _compute_diff(self, original: JulesSessionState, current: JulesSessionState) -> dict[str, Any]:
        \"\"\"Compute dictionary of changed fields for LangGraph checkpointer.\"\"\"
        updates = {}
        for field in current.model_fields:
            old_val = getattr(original, field)
            new_val = getattr(current, field)
            if old_val != new_val:
                updates[field] = new_val
        return updates
"""

if "_compute_diff" not in text:
    init_end = text.find("    async def monitor_session")
    text = text[:init_end] + diff_method + "\n" + text[init_end:]

def replace_node(name):
    global text
    pattern = r"async def " + name + r"\(self, state: JulesSessionState\) -> JulesSessionState"
    match = re.search(pattern, text)
    if not match:
        print(f"Could not find signature for {name}")
        return
        
    sig = match.group(0)
    new_sig = sig.replace("state: JulesSessionState", "_state_in: JulesSessionState").replace("-> JulesSessionState", "-> dict[str, Any]")
    text = text[:match.start()] + new_sig + text[match.end():]
    
    match_start = text.find(new_sig)
    
    fn_body_start = text.find(":", match_start) + 1
    next_newline = text.find("\n", fn_body_start)
    next_line_start = next_newline + 1
    
    docstring_match = re.search(r'^\s*"""[\s\S]*?"""', text[next_line_start:])
    if docstring_match:
        insert_pos = next_line_start + docstring_match.end()
    else:
        insert_pos = next_line_start
        
    next_def = re.search(r'\n    (?:async )?def ', text[insert_pos:])
    fn_end = insert_pos + next_def.start() if next_def else len(text)
    
    fn_text = text[insert_pos:fn_end]
    fn_text = re.sub(r'\breturn state\b', r'return self._compute_diff(_state_in, state)', fn_text)
    if name == "validate_completion":
        fn_text = re.sub(r'\breturn distress_state\b', r'return self._compute_diff(_state_in, distress_state)', fn_text)
        
    text = text[:insert_pos] + "\n        state = _state_in.model_copy(deep=True)\n" + fn_text + text[fn_end:]

nodes = ["monitor_session", "answer_inquiry", "validate_completion", "check_pr", "request_pr_creation", "wait_for_pr"]
for node in nodes:
    replace_node(node)

with open(file_path, "w") as f:
    f.write(text)
print("Refactoring complete.")

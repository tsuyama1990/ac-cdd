import asyncio
import json

import httpx
from ac_cdd_core.services.jules_client import JulesClient


async def dump_activities(session_id: str):
    client = JulesClient()

    # Ensure ID doesn't have duplicate prefix
    if session_id.startswith("sessions/"):
        sid = session_id
    else:
        sid = f"sessions/{session_id}"

    url = f"{client.base_url}/{sid}/activities?pageSize=100"
    print(f"Fetching activities from: {url}")

    headers = client._get_headers()

    async with httpx.AsyncClient() as http:
        try:
            resp = await http.get(url, headers=headers)
            print(f"Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                activities = data.get("activities", [])
                print(f"Found {len(activities)} activities.")

                # Sort by createTime if possible, usually API order is irrelevant or newest last?
                # We'll just dump them all to a file for inspection.
                output_file = "debug_activities_dump.json"
                with open(output_file, "w") as f:
                    json.dump(activities, f, indent=2)
                print(f"Dumped to {output_file}")

                # Print the last 5 activities summary to console
                print("\n--- Last 5 Activities ---")
                for act in activities[-5:]:
                    print(f"Type: {act.keys()}")
                    if "agentMessaged" in act:
                        print(f"MSG: {act['agentMessaged'].get('agentMessage')}")
                    if "agentThought" in act:
                        print(f"THOUGHT: {act['agentThought'].get('thought')}")

            else:
                print(f"Error: {resp.text}")
        except Exception as e:
            print(f"Exception: {e}")


if __name__ == "__main__":
    import sys

    # Default to the session reported by user if no arg provided
    target_session = "8497207105819446593"
    if len(sys.argv) > 1:
        target_session = sys.argv[1]

    asyncio.run(dump_activities(target_session))

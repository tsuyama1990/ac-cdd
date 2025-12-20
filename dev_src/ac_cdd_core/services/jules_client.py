import asyncio
import json
import time
import re
import urllib.request
import urllib.error
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from ac_cdd_core.config import settings
from ac_cdd_core.utils import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

console = Console()

# --- Exception Classes ---
class JulesSessionError(Exception):
    pass

class JulesTimeoutError(JulesSessionError):
    pass

class JulesApiError(Exception):
    pass

# --- API Client Implementation ---
class JulesApiClient:
    BASE_URL = "https://jules.googleapis.com/v1alpha"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.JULES_API_KEY
        if not self.api_key:
            from dotenv import load_dotenv
            load_dotenv()
            self.api_key = os.getenv("JULES_API_KEY") or os.getenv("GOOGLE_API_KEY")
        
        if not self.api_key:
            # Last ditch attempt
            try:
                if Path(".env").exists():
                    content = Path(".env").read_text()
                    for line in content.splitlines():
                        if line.startswith("JULES_API_KEY="):
                            self.api_key = line.split("=", 1)[1].strip().strip('"')
            except Exception:
                pass
            
        if not self.api_key:
             raise ValueError("API Key not found for Jules API.")

        self.headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json"
        }

    def _request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/{endpoint}"
        body = json.dumps(data).encode("utf-8") if data else None
        
        req = urllib.request.Request(url, method=method, headers=self.headers, data=body)
        
        try:
            with urllib.request.urlopen(req) as response:
                resp_body = response.read().decode("utf-8")
                if not resp_body:
                    return {}
                return json.loads(resp_body)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise JulesApiError(f"404 Not Found: {url}")
            err_msg = e.read().decode("utf-8")
            logger.error(f"Jules API Error {e.code}: {err_msg}")
            raise JulesApiError(f"API request failed: {e.code} {err_msg}") from e
        except Exception as e:
            logger.error(f"Network Error: {e}")
            raise JulesApiError(f"Network request failed: {e}") from e

    def list_sources(self) -> List[Dict[str, Any]]:
        data = self._request("GET", "sources")
        return data.get("sources", [])

    def find_source_by_repo(self, repo_name: str) -> Optional[str]:
        sources = self.list_sources()
        for src in sources:
            if repo_name in src.get("name", ""):
                 return src["name"]
        return None

    def create_session(self, source: str, prompt: str) -> Dict[str, Any]:
        payload = {
            "prompt": prompt,
            "sourceContext": {
                "source": source,
                "githubRepoContext": {
                    "startingBranch": "main"
                }
            }
        }
        return self._request("POST", "sessions", payload)

    def list_activities(self, session_id_path: str) -> List[Dict[str, Any]]:
        try:
            resp = self._request("GET", f"{session_id_path}/activities?pageSize=50")
            return resp.get("activities", [])
        except JulesApiError as e:
            if "404" in str(e):
                return []
            raise


# --- Service Client Implementation ---
class JulesClient:
    """
    Client for interacting with the Jules Autonomous Agent via REST API.
    """

    def __init__(self) -> None:
        self.api_client = JulesApiClient()
        self.timeout = settings.jules.timeout_seconds
        self.polling_interval = 20
        self.console = Console()
        self.repo_name = "template_cli_agent" 

    async def run_session(
        self,
        session_id: str,
        prompt: str,
        files: list[str],
        completion_signal_file: Path,
        timeout_override: int | None = None
    ) -> dict[str, Any]:
        
        # 1. Find Source
        logger.info(f"Finding Jules Source for {self.repo_name}...")
        source = self.api_client.find_source_by_repo(self.repo_name)
        if not source:
            sources = self.api_client.list_sources()
            if sources:
                source = sources[0]["name"]
                logger.warning(f"Using fallback source: {source}")
            else:
                 raise JulesSessionError("No Jules Sources found!")

        # 2. Prepare Prompt
        file_context = ""
        for file_path in files:
            p = Path(file_path)
            if p.exists():
                content = p.read_text(encoding="utf-8")
                file_context += f"\n=== FILE: {p.name} ===\n{content}\n"
        
        full_prompt = (
            f"{prompt}\n\n"
            f"=== CONTEXT FILES (Current Local State) ===\n"
            f"{file_context}\n\n"
            f"=== IMPORTANT INSTRUCTION ===\n"
            f"Since I am using the API directly, please OUTPUT the content of the generated files in Markdown Code Blocks.\n"
            f"Format:\n"
            f"FILENAME: path/to/file\n"
            f"```ext\n"
            f"content\n"
            f"```\n"
            f"Start with SYSTEM_ARCHITECTURE.md, then the cycle files.\n"
            f"Finally, output the SIGNAL JSON in a block labelled 'SIGNAL'."
        )

        logger.info(f"Creating Jules Session...")
        
        try:
            resp = await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: self.api_client.create_session(source, full_prompt)
            )
            
            session_name = resp.get("name")
            if not session_name:
                raise JulesSessionError(f"Failed to create session. Response: {resp}")
            
            logger.info(f"Session Created: {session_name}")
            # RESTORED: Explicitly print the URL for the user
            self.console.print(f"[bold green]Jules Session Active[/bold green]: https://jules.google/sessions/{session_name.split('/')[-1]}")
            
            return await self._poll_activities(session_name, completion_signal_file, timeout_override or self.timeout)

        except JulesApiError as e:
            raise JulesSessionError(f"Jules API failed: {e}") from e

    async def _poll_activities(self, session_name: str, signal_file: Path, timeout: int) -> Dict[str, Any]:
        start_time = time.time()
        seen_activities = set()
        
        with self.console.status(f"[bold green]Waiting for Jules ({session_name})...") as status:
            while time.time() - start_time < timeout:
                try:
                    activities = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: self.api_client.list_activities(session_name)
                    )
                    
                    for act in activities:
                        act_id = act.get("name")
                        if act_id in seen_activities:
                            continue
                        seen_activities.add(act_id)
                        
                        # Extract Text
                        text_content = ""
                        if "text" in act: 
                            text_content = act["text"]
                        elif "message" in act:
                             text_content = str(act["message"])

                        if text_content:
                            # Print only a snippet to console to avoid spam
                            snippet = text_content[:100].replace("\n", " ") + "..."
                            self.console.print(f"[dim]Jules: {snippet}[/dim]")
                            
                            self._parse_and_write_files(text_content)
                            
                            # Check for Signal
                            if "SIGNAL" in text_content or "plan_status.json" in text_content:
                                match = re.search(r"\{.*\"status\":.*\"completed\".*\}", text_content, re.DOTALL)
                                if match:
                                    json_str = match.group(0)
                                    try:
                                        data = json.loads(json_str)
                                        signal_file.parent.mkdir(parents=True, exist_ok=True)
                                        signal_file.write_text(json_str, encoding="utf-8")
                                        return data
                                    except:
                                        pass

                except JulesApiError as e:
                    pass # Retry on transient errors
                
                await asyncio.sleep(self.polling_interval)
                
        raise JulesTimeoutError("Timed out waiting for Jules API response.")

    def _parse_and_write_files(self, text: str) -> None:
        pattern = r"FILENAME:\s*([^\n]+)\n```\w*\n(.*?)```"
        matches = re.finditer(pattern, text, re.DOTALL)
        
        for m in matches:
            fname = m.group(1).strip()
            content = m.group(2)
            
            if "dev_documents" in fname or "SYSTEM_ARCHITECTURE" in fname:
                full_path = Path(settings.paths.documents_dir).parent / fname
                try:
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(content, encoding="utf-8")
                    self.console.print(f"[green] Generated: {fname}[/green]")
                except Exception as e:
                    logger.error(f"Failed to write parse file {fname}: {e}")

    async def _sync_files(self, session_id: str) -> None:
        pass

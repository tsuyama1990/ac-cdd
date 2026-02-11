import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ac_cdd_core.config import settings
from ac_cdd_core.utils import logger
from dotenv import load_dotenv


class JulesApiError(Exception):
    pass


class JulesApiClient:
    BASE_URL = "https://jules.googleapis.com/v1alpha"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.JULES_API_KEY
        if not self.api_key:
            load_dotenv()
            self.api_key = os.getenv("JULES_API_KEY") or os.getenv("GOOGLE_API_KEY")

        if not self.api_key:
            self._try_load_key_from_env_file()

        if not self.api_key:
            self._ensure_api_key_or_raise()

        self.headers: dict[str, str] = {
            "x-goog-api-key": str(self.api_key or ""),
            "Content-Type": "application/json",
        }

    def _try_load_key_from_env_file(self) -> None:
        try:
            if Path(".env").exists():
                content = Path(".env").read_text()
                for line in content.splitlines():
                    key_part = line.split("=", 1)[0].strip()
                    if key_part in ["JULES_API_KEY", "GOOGLE_API_KEY"]:
                        parts = line.split("=", 1)
                        if len(parts) > 1:
                            candidate = parts[1].strip().strip('"').strip("'")
                            if candidate:
                                self.api_key = candidate
                                return
        except Exception:
            logger.debug("Skipping malformed .env line during key check.")

    def _ensure_api_key_or_raise(self) -> None:
        if os.environ.get("AC_CDD_AUTO_APPROVE") or "PYTEST_CURRENT_TEST" in os.environ:
            logger.warning("Jules API Key missing in Test Environment. Using dummy key.")
            self.api_key = "dummy_jules_key"
            return

        msg = (
            "API Key not found for Jules API. "
            "Please set JULES_API_KEY or GOOGLE_API_KEY in your .env file or environment variables. "
            "Note: If you have the variable in .env, ensure it is not empty."
        )
        raise ValueError(msg)

    def _request(
        self, method: str, endpoint: str, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if self.api_key == "dummy_jules_key":
            return self._handle_dummy_request(method, endpoint)

        url = f"{self.BASE_URL}/{endpoint}"
        body = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, method=method, headers=self.headers, data=body)  # noqa: S310

        try:
            with urllib.request.urlopen(req) as response:  # noqa: S310
                resp_body = response.read().decode("utf-8")
                return dict(json.loads(resp_body)) if resp_body else {}
        except urllib.error.HTTPError as e:
            if e.code == 404:
                msg = f"404 Not Found: {url}"
                raise JulesApiError(msg) from e
            err_msg = e.read().decode("utf-8")
            logger.error(f"Jules API Error {e.code}: {err_msg}")
            emsg = f"API request failed: {e.code} {err_msg}"
            raise JulesApiError(emsg) from e
        except Exception as e:
            logger.error(f"Network Error: {e}")
            emsg = f"Network request failed: {e}"
            raise JulesApiError(emsg) from e

    def _handle_dummy_request(self, method: str, endpoint: str) -> dict[str, Any]:
        logger.info(f"Test Mode: Returning dummy response for {method} {endpoint}")
        if endpoint.endswith("sessions"):
            return {"name": "sessions/dummy-session-123"}
        if "activities" in endpoint:
            return {"activities": []}
        if endpoint.endswith("sources"):
            return {"sources": [{"name": "sources/github/test-owner/test-repo"}]}
        if "approvePlan" in endpoint:
            return {}
        return {}

    def list_sources(self) -> list[dict[str, Any]]:
        data = self._request("GET", "sources")
        return list(data.get("sources", []))

    def find_source_by_repo(self, repo_name: str) -> str | None:
        sources = self.list_sources()
        for src in sources:
            if repo_name in str(src.get("name", "")):
                return str(src["name"])
        return None

    def create_session(
        self,
        source: str,
        prompt: str,
        require_plan_approval: bool = False,
        branch: str = "main",
        title: str | None = None,
        automation_mode: str = "AUTO_CREATE_PR",
    ) -> dict[str, Any]:
        payload = {
            "prompt": prompt,
            "sourceContext": {
                "source": source,
                "githubRepoContext": {"startingBranch": branch},
            },
            "requirePlanApproval": require_plan_approval,
            "automationMode": automation_mode,
        }
        if title:
            payload["title"] = title
        return self._request("POST", "sessions", payload)

    def approve_plan(self, session_id: str, plan_id: str) -> dict[str, Any]:
        """Approves the current plan in the session, triggering implementation."""
        endpoint = f"{session_id}:approvePlan"
        payload: dict[str, Any] = {}
        return self._request("POST", endpoint, payload)

    def list_activities(self, session_id_path: str) -> list[dict[str, Any]]:
        all_activities = []
        page_token = ""
        try:
            while True:
                url = f"{session_id_path}/activities?pageSize=100"
                if page_token:
                    url += f"&pageToken={page_token}"

                resp = self._request("GET", url)
                acts = list(resp.get("activities", []))
                if not acts:
                    break
                all_activities.extend(acts)

                page_token = resp.get("nextPageToken", "")
                if not page_token:
                    break
        except JulesApiError as e:
            if "404" in str(e):
                return []
            raise

        return all_activities

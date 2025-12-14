import json
from pathlib import Path
from typing import Any, Optional

import httpx

from src.agent_interface import AgentInterface


class JulesApiClient(AgentInterface):
    """
    Agent interface implementation for the Jules REST API.
    Manages session state and communicates with the Jules API.
    """
    BASE_URL = "https://jules.googleapis.com/v1alpha"
    STATE_FILE = Path(".jules/session_state.json")

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.Client(
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )
        self.STATE_FILE.parent.mkdir(exist_ok=True)

    def _get_session_id(self) -> Optional[str]:
        if not self.STATE_FILE.exists():
            return None
        try:
            data = json.loads(self.STATE_FILE.read_text())
            return data.get("last_session_id")
        except (json.JSONDecodeError, IOError):
            return None

    def _save_session_id(self, session_id: str):
        self.STATE_FILE.write_text(json.dumps({"last_session_id": session_id}))

    def start_task(self, prompt: str, **kwargs: Any) -> str:
        """
        Starts a new task by creating a new session via the API.
        """
        session_name = kwargs.get("session_name")
        payload = {"prompt": prompt}
        if session_name:
            payload["session_name"] = session_name

        try:
            response = self.client.post(
                f"{self.BASE_URL}/sessions",
                json=payload
            )
            response.raise_for_status()
            session_data = response.json()
            session_id = session_data.get("name")
            if session_id:
                self._save_session_id(session_id)
                return f"API session '{session_id}' created successfully."
            raise ConnectionError("Failed to create API session: No session ID in response.")
        except httpx.HTTPStatusError as e:
            raise ConnectionError(f"API Error: {e.response.status_code} - {e.response.text}") from e
        except httpx.RequestError as e:
            raise ConnectionError(f"Request Error: {e}") from e

    def send_message(self, prompt: str, **kwargs: Any) -> str:
        """
        Sends a message to the currently active session.
        """
        session_id = self._get_session_id()
        if not session_id:
            return self.start_task(prompt, **kwargs)

        try:
            response = self.client.post(
                f"{self.BASE_URL}/{session_id}:sendMessage",
                json={"prompt": prompt}
            )
            response.raise_for_status()
            return f"Message sent to session '{session_id}' successfully."
        except httpx.HTTPStatusError as e:
            raise ConnectionError(f"API Error: {e.response.status_code} - {e.response.text}") from e
        except httpx.RequestError as e:
            raise ConnectionError(f"Request Error: {e}") from e

    def get_status(self) -> str:
        """
        Returns the ID of the last active session.
        """
        session_id = self._get_session_id()
        if session_id:
            return f"Current active session ID: {session_id}"
        return "No active session found."

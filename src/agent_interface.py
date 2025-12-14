from abc import ABC, abstractmethod
from typing import Any


class AgentInterface(ABC):
    """
    Abstract base class for agent communication.
    """

    @abstractmethod
    def start_task(self, prompt: str, **kwargs: Any) -> str:
        """
        Starts a new task with the given prompt.
        """
        pass

    @abstractmethod
    def send_message(self, prompt: str, **kwargs: Any) -> str:
        """
        Sends a message to the current session.
        """
        pass

    @abstractmethod
    def get_status(self) -> str:
        """
        Gets the status of the current session.
        """
        pass

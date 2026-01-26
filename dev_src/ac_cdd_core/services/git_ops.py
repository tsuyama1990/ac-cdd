from .git.base import BaseGitManager
from .git.branching import GitBranchingMixin
from .git.checkout import GitCheckoutMixin
from .git.merging import GitMergingMixin
from .git.state import GitStateMixin


class GitManager(
    GitBranchingMixin, GitCheckoutMixin, GitMergingMixin, GitStateMixin, BaseGitManager
):
    """
    Manages Git operations for the AC-CDD workflow.
    Refactored to composite mixins for better maintainability.
    """

    # Re-expose constant for compatibility if anything imports it directly
    STATE_BRANCH = "ac-cdd/state"

    def __init__(self) -> None:
        super().__init__()

from dataclasses import dataclass

from ac_cdd_core.services.artifacts import ArtifactManager
from ac_cdd_core.services.contracts import ContractManager
from ac_cdd_core.services.file_ops import FilePatcher
from ac_cdd_core.services.git_ops import GitManager
from ac_cdd_core.services.jules_client import JulesClient
from ac_cdd_core.services.llm_reviewer import LLMReviewer


@dataclass
class ServiceContainer:
    file_patcher: FilePatcher
    contract_manager: ContractManager
    artifact_manager: ArtifactManager
    jules: JulesClient | None = None
    reviewer: LLMReviewer | None = None
    git: GitManager | None = None

    @classmethod
    def default(cls) -> "ServiceContainer":
        return cls(
            file_patcher=FilePatcher(),
            contract_manager=ContractManager(),
            artifact_manager=ArtifactManager(),
            jules=JulesClient(),
            reviewer=LLMReviewer(),
            git=GitManager(),
        )

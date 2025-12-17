from dataclasses import dataclass

from ac_cdd.presentation import ConsolePresenter
from ac_cdd.services.artifacts import ArtifactManager
from ac_cdd.services.contracts import ContractManager
from ac_cdd.services.file_ops import FilePatcher


@dataclass
class ServiceContainer:
    file_patcher: FilePatcher
    contract_manager: ContractManager
    artifact_manager: ArtifactManager
    presenter: ConsolePresenter

    @classmethod
    def default(cls) -> "ServiceContainer":
        return cls(
            file_patcher=FilePatcher(),
            contract_manager=ContractManager(),
            artifact_manager=ArtifactManager(),
            presenter=ConsolePresenter(),
        )

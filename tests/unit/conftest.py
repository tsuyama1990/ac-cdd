from unittest.mock import MagicMock

import pytest
from ac_cdd_core.service_container import ServiceContainer


@pytest.fixture
def mock_file_patcher():
    return MagicMock()


@pytest.fixture
def mock_contract_manager():
    return MagicMock()


@pytest.fixture
def mock_artifact_manager():
    return MagicMock()


@pytest.fixture
def mock_presenter():
    presenter = MagicMock()
    presenter.review_and_confirm.return_value = True
    return presenter


@pytest.fixture
def mock_services(mock_file_patcher, mock_contract_manager, mock_artifact_manager, mock_presenter):
    return ServiceContainer(
        file_patcher=mock_file_patcher,
        contract_manager=mock_contract_manager,
        artifact_manager=mock_artifact_manager,
        presenter=mock_presenter,
    )


@pytest.fixture
def mock_agent_result():
    def _create_result(output_data):
        result = MagicMock()
        result.output = output_data
        return result

    return _create_result

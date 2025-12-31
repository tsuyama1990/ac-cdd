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
def mock_jules():
    return MagicMock()


@pytest.fixture
def mock_reviewer():
    return MagicMock()


@pytest.fixture
def mock_git():
    return MagicMock()


@pytest.fixture
def mock_services(
    mock_file_patcher,
    mock_contract_manager,
    mock_artifact_manager,
    mock_presenter,
    mock_jules,
    mock_reviewer,
    mock_git,
):
    return ServiceContainer(
        file_patcher=mock_file_patcher,
        contract_manager=mock_contract_manager,
        artifact_manager=mock_artifact_manager,
        jules=mock_jules,
        reviewer=mock_reviewer,
        git=mock_git,
    )


@pytest.fixture
def mock_agent_result():
    def _create_result(output_data):
        result = MagicMock()
        result.output = output_data
        return result

    return _create_result

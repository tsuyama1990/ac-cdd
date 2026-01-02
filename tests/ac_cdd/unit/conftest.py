from unittest.mock import MagicMock, patch

import pytest
from ac_cdd_core.config import Settings
from ac_cdd_core.service_container import ServiceContainer


@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    """Mock the global settings object and env vars for all unit tests."""
    # Pre-emptively set environment variables to avoid pydantic-ai import errors
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy_key_for_test")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key_for_test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy_key_for_test")
    monkeypatch.setenv("JULES_API_KEY", "dummy_key_for_test")
    monkeypatch.setenv("E2B_API_KEY", "dummy_key_for_test")

    # Create a default Settings object (using defaults defined in class)
    try:
        real_defaults = Settings()
    except Exception:
        # Fallback if creation fails (e.g. missing required env vars if any)
        real_defaults = MagicMock()

    with patch("ac_cdd_core.config.settings", real_defaults):
        yield real_defaults


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

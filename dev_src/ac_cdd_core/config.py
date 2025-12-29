import importlib.util
import sys
from pathlib import Path


def load_user_config():
    """
    Loads ac_cdd_config.py from the current working directory.
    This allows the tool to run as an installed package without relying on specific structure.
    """
    cwd = Path.cwd()
    config_path = cwd / "ac_cdd_config.py"

    if not config_path.exists():
        # Fallback for development/testing if not in CWD but relative to this file
        # This preserves behavior for local development of the tool itself if running from repo root
        dev_path = Path(__file__).parents[2] / "ac_cdd_config.py"
        if dev_path.exists():
            config_path = dev_path
        else:
            raise ImportError(
                f"Configuration file not found at {config_path}. "
                "Please ensure ac_cdd_config.py exists in the current directory."
            )

    try:
        spec = importlib.util.spec_from_file_location("ac_cdd_config", config_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load spec from {config_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules["ac_cdd_config"] = module
        spec.loader.exec_module(module)
        return module.config
    except Exception as e:
        raise ImportError(f"Failed to load configuration from {config_path}: {e}") from e


settings = load_user_config()
config = settings

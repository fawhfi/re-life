import ast
import importlib
import os
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import config
import pytest


@contextmanager
def _reloaded_config(overrides):
    try:
        with patch.dict(os.environ, overrides, clear=True):
            yield importlib.reload(config)
    finally:
        importlib.reload(config)


def test_security_settings_use_safe_defaults():
    with _reloaded_config({}) as reloaded:
        assert reloaded.APP_ENV == "development"
        assert reloaded.IS_DEVELOPMENT is True
        assert reloaded.IS_PRODUCTION is False
        assert reloaded.ALLOW_DEV_AUTH_CODES is False
        assert reloaded.SESSION_COOKIE_NAME == "rel_session"
        assert reloaded.SESSION_IDLE_DAYS == 30
        assert reloaded.SESSION_IDLE_SECONDS == 30 * 24 * 60 * 60


def test_security_settings_are_loaded_from_environment():
    metadata_hash_key = "independent-production-metadata-key"
    with _reloaded_config(
        {
            "APP_ENV": "production",
            "ALLOW_DEV_AUTH_CODES": "true",
            "SESSION_COOKIE_NAME": "production_session",
            "SESSION_IDLE_DAYS": "45",
            "SESSION_METADATA_HASH_KEY": metadata_hash_key,
        }
    ) as reloaded:
        assert reloaded.APP_ENV == "production"
        assert reloaded.IS_PRODUCTION is True
        assert reloaded.IS_DEVELOPMENT is False
        assert reloaded.ALLOW_DEV_AUTH_CODES is False
        assert reloaded.SESSION_COOKIE_NAME == "production_session"
        assert reloaded.SESSION_IDLE_DAYS == 45
        assert reloaded.SESSION_IDLE_SECONDS == 45 * 24 * 60 * 60
        assert reloaded.SESSION_METADATA_HASH_KEY == metadata_hash_key


def test_development_can_enable_dev_auth_codes():
    with _reloaded_config(
        {"APP_ENV": "development", "ALLOW_DEV_AUTH_CODES": "true"}
    ) as reloaded:
        assert reloaded.ALLOW_DEV_AUTH_CODES is True


def test_invalid_app_env_is_rejected():
    with pytest.raises(RuntimeError, match="APP_ENV"):
        with _reloaded_config({"APP_ENV": "prodution"}):
            pass


def _is_explicit_dotenv_statement(node):
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return False

    call = node.value
    return (
        isinstance(call.func, ast.Name)
        and call.func.id == "load_dotenv"
        and len(call.args) == 1
        and not call.keywords
        and isinstance(call.args[0], ast.BinOp)
        and isinstance(call.args[0].op, ast.Div)
        and isinstance(call.args[0].left, ast.Name)
        and call.args[0].left.id == "root_dir"
        and isinstance(call.args[0].right, ast.Constant)
        and call.args[0].right.value == ".env"
    )


def _assert_dotenv_precedes_local_imports(source, project_root):
    tree = ast.parse(source)
    local_modules = {
        path.stem
        for path in project_root.glob("*.py")
        if path.name not in {"main.py", "__init__.py"}
    }
    local_packages = {
        path.name
        for path in project_root.iterdir()
        if path.is_dir() and (path / "__init__.py").is_file()
    }
    local_import_roots = local_modules | local_packages

    dotenv_statements = [
        node for node in tree.body if _is_explicit_dotenv_statement(node)
    ]
    assert len(dotenv_statements) == 1, (
        'main.py must execute load_dotenv(root_dir / ".env") as a top-level expression'
    )

    local_import_lines = [
        node.lineno
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and (
            (
                isinstance(node, ast.Import)
                and any(
                    alias.name.split(".", 1)[0] in local_import_roots
                    for alias in node.names
                )
            )
            or (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.split(".", 1)[0] in local_import_roots
            )
        )
    ]

    assert local_import_lines
    assert dotenv_statements[0].lineno < min(local_import_lines), (
        "load_dotenv must execute before local module or package imports"
    )


def test_main_loads_dotenv_before_local_imports():
    main_path = Path(__file__).parents[1] / "main.py"
    _assert_dotenv_precedes_local_imports(
        main_path.read_text(encoding="utf-8"), main_path.parent
    )


def test_dotenv_order_check_rejects_call_inside_uncalled_function():
    project_root = Path(__file__).parents[1]
    nested_call_source = """
from pathlib import Path
from dotenv import load_dotenv

root_dir = Path(__file__).parent

def load_environment():
    load_dotenv(root_dir / ".env")

from config import APP_ENV
"""

    with pytest.raises(AssertionError, match="top-level expression"):
        _assert_dotenv_precedes_local_imports(nested_call_source, project_root)


def test_dotenv_order_check_includes_local_package_imports():
    project_root = Path(__file__).parents[1]
    package_import_first_source = """
from pathlib import Path
from dotenv import load_dotenv

root_dir = Path(__file__).parent

from nlp import __all__

load_dotenv(root_dir / ".env")
"""

    with pytest.raises(
        AssertionError, match="before local module or package imports"
    ):
        _assert_dotenv_precedes_local_imports(
            package_import_first_source, project_root
        )

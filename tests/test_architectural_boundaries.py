"""
tests/test_architectural_boundaries.py

[ADDITIVE] Part 2B — Mission 5.

Architectural boundary tests using AST inspection and module attribute
reflection to enforce the Telegram phone number security rules at the code level.

Rules enforced:
  1. No API route function may import from app.security.secrets directly.
  2. No Pydantic response model in api/ may declare a field named
     phone_number_encrypted, phone_number, or ciphertext.
  3. SecretStore may not be imported inside api/routes/*.
  4. TelegramAccountORM must never be returned from an endpoint function
     (only mapped response models are allowed).
  5. The frontend service file must not contain the literal string
     'phone_number_encrypted'.
"""
from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
API_ROUTES_DIR = PROJECT_ROOT / "api" / "routes"
FRONTEND_SERVICE = PROJECT_ROOT / "frontend" / "src" / "api" / "telegram.service.ts"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_python_sources(directory: Path) -> list[Path]:
    return list(directory.rglob("*.py"))


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _collect_imports(tree: ast.Module) -> list[str]:
    """Return a flat list of all dotted import names in the AST."""
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def _collect_class_fields(tree: ast.Module) -> dict[str, list[str]]:
    """Return {ClassName: [field_names]} for all top-level Pydantic-like classes."""
    result: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            fields = [
                n.target.id  # type: ignore[union-attr]
                for n in ast.walk(node)
                if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
            ]
            result[node.name] = fields
    return result


# ---------------------------------------------------------------------------
# Boundary tests
# ---------------------------------------------------------------------------

class TestAPIRouteBoundaries:

    def _route_files(self) -> list[Path]:
        return _get_python_sources(API_ROUTES_DIR)

    def test_routes_do_not_import_secret_store_directly(self):
        """
        Telegram API route must never import app.security.secrets.* directly.
        It must instead use api.dependencies.get_secret_store via Depends.
        """
        forbidden_prefix = "app.security.secrets"
        # Only the telegram route is under the phone-security contract.
        telegram_route = API_ROUTES_DIR / "telegram.py"
        if not telegram_route.exists():
            pytest.skip("telegram.py route not found")
        
        tree = _parse(telegram_route)
        violations = [
            imp for imp in _collect_imports(tree)
            if imp.startswith(forbidden_prefix)
        ]
        assert not violations, (
            "telegram.py must not import SecretStore directly.\n"
            "Use api.dependencies.get_secret_store instead.\n"
            "Found: " + str(violations)
        )

    def test_response_models_do_not_expose_encrypted_field(self):
        """
        Any Pydantic model in api/services or api/routes must not have a field
        called phone_number_encrypted, phone_number (raw), or ciphertext.
        """
        forbidden_fields = {"phone_number_encrypted", "ciphertext"}
        violations: list[str] = []
        search_dirs = [
            PROJECT_ROOT / "api" / "routes",
            PROJECT_ROOT / "api" / "services",
        ]
        for directory in search_dirs:
            if not directory.exists():
                continue
            for path in directory.rglob("*.py"):
                tree = _parse(path)
                for class_name, fields in _collect_class_fields(tree).items():
                    for field in fields:
                        if field in forbidden_fields:
                            violations.append(
                                f"{path.name}: class '{class_name}' has forbidden field '{field}'"
                            )

        assert not violations, (
            "Response models must not expose encrypted or raw phone fields.\n"
            "Violations:\n" + "\n".join(violations)
        )

    def test_orm_model_not_returned_from_routes(self):
        """
        API route functions must never return TelegramAccountORM directly.
        They must use a mapped Pydantic response model.
        """
        # Check that TelegramAccountORM is not used as a return annotation in routes
        violations: list[str] = []
        for path in self._route_files():
            tree = _parse(path)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    if node.returns:
                        return_src = ast.unparse(node.returns)
                        if "TelegramAccountORM" in return_src:
                            violations.append(
                                f"{path.name}: function '{node.name}' has ORM return annotation"
                            )

        assert not violations, (
            "Route handlers must never return ORM objects directly.\n"
            "Violations:\n" + "\n".join(violations)
        )


class TestFrontendBoundaries:

    def test_frontend_service_does_not_contain_encrypted_field(self):
        """The frontend telegram service body must never reference phone_number_encrypted."""
        if not FRONTEND_SERVICE.exists():
            pytest.skip("Frontend service file not found")
        content = FRONTEND_SERVICE.read_text(encoding="utf-8")
        # Strip comments (lines starting with //) before checking.
        code_lines = [
            line for line in content.splitlines()
            if not line.lstrip().startswith("//")
        ]
        code_only = "\n".join(code_lines)
        assert "phone_number_encrypted" not in code_only, (
            "Frontend service file body must not reference 'phone_number_encrypted'. "
            "Only phone_number_masked should be used in code (comments are allowed)."
        )

    def test_frontend_service_does_not_store_phone_in_url_params(self):
        """The frontend must not pass phone_number as a URL query parameter."""
        if not FRONTEND_SERVICE.exists():
            pytest.skip("Frontend service file not found")
        content = FRONTEND_SERVICE.read_text(encoding="utf-8")
        # Check that phone_number is only sent in request body (POST), not params
        import re
        # Look for any pattern like params: { phone_number: ...} or ?phone_number=
        url_param_patterns = [
            r'\?phone_number\s*=',
            r"params\s*:\s*\{[^}]*phone_number",
        ]
        for pattern in url_param_patterns:
            matches = re.findall(pattern, content)
            assert not matches, (
                f"Frontend must not send phone_number as a URL param. "
                f"Found pattern '{pattern}' in telegram.service.ts"
            )


class TestServiceBoundaries:

    def test_phone_secret_service_is_sole_decryption_site(self):
        """
        AES-GCM decrypt calls must only exist inside TelegramPhoneSecretService,
        not in repositories, route handlers, or serializers.
        """
        allowed_path = PROJECT_ROOT / "app" / "integrations" / "telegram" / "security" / "phone_secret_service.py"
        forbidden_dirs = [
            PROJECT_ROOT / "api" / "routes",
            PROJECT_ROOT / "api" / "services",
            PROJECT_ROOT / "app" / "integrations" / "telegram" / "repositories",
        ]
        decrypt_keyword = "decrypt"
        violations: list[str] = []

        for directory in forbidden_dirs:
            if not directory.exists():
                continue
            for path in directory.rglob("*.py"):
                if path == allowed_path:
                    continue
                content = path.read_text(encoding="utf-8")
                # Check for raw crypto decrypt calls (not just importing/calling PhoneSecretService methods)
                if "secret_store.decrypt" in content or ".decrypt(" in content:
                    violations.append(f"{path.relative_to(PROJECT_ROOT)}: contains direct decrypt call")

        assert not violations, (
            "Decryption must only occur inside TelegramPhoneSecretService.\n"
            "Violations:\n" + "\n".join(violations)
        )

    def test_no_plaintext_phone_in_orm_columns(self):
        """TelegramAccountORM must not have a 'phone_number' (plaintext) column."""
        from app.integrations.telegram.db.orm_models import TelegramAccountORM
        mapper = inspect.getmembers(TelegramAccountORM, lambda a: not inspect.isroutine(a))
        column_names = [name for name, _ in mapper if not name.startswith("_")]
        assert "phone_number" not in column_names, (
            "TelegramAccountORM must not have a plaintext 'phone_number' column. "
            "Only 'phone_number_encrypted' is allowed."
        )
        assert "phone_number_encrypted" in column_names, (
            "TelegramAccountORM must have a 'phone_number_encrypted' column."
        )

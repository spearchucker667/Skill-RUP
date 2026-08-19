"""
Deep ecosystem tooling detection for RUP runtime.
Covers Python, JS/TS, Go, Rust, CI/CD, Containers, IaC, and Monorepos.
"""
import json
import warnings
from pathlib import Path
from typing import Dict, Any, List, Optional

class ToolDetector:
    def __init__(self, target_dir: Path):
        self.target_dir = target_dir

    def detect_all(self, languages: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Run all tooling detections."""
        return {
            "test_framework": self.detect_test_framework(),
            "linter": self.detect_linter(),
            "formatter": self.detect_formatter(),
            "type_checker": self.detect_type_checker(),
            "ci_platform": self.detect_ci_platform(),
            "containerization": self.detect_containerization(),
            "iac": self.detect_iac(),
            "monorepo": self.detect_monorepo(),
            "build_tool": self.detect_build_tool()
        }

    def detect_test_framework(self) -> Optional[str]:
        """Detect the primary test framework."""
        # Python
        if (self.target_dir / "pytest.ini").exists():
            return "pytest"
        if (self.target_dir / "pyproject.toml").exists():
            try:
                content = (self.target_dir / "pyproject.toml").read_text(encoding="utf-8", errors="ignore")
                if "tool.pytest" in content or "pytest" in content:
                    return "pytest"
            except Exception as e:
                warnings.warn(f"Tool detection warning: {e}", RuntimeWarning, stacklevel=2)
        if list(self.target_dir.glob("**/test_*.py")) or list(self.target_dir.glob("**/*_test.py")):
            return "pytest"

        # JS / TS
        pkg_json = self.target_dir / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                scripts = data.get("scripts", {})
                if "vitest" in deps or any("vitest" in s for s in scripts.values()):
                    return "vitest"
                if "jest" in deps or any("jest" in s for s in scripts.values()):
                    return "jest"
                if "mocha" in deps or any("mocha" in s for s in scripts.values()):
                    return "mocha"
                if "test" in scripts:
                    return "npm-test"
            except Exception as e:
                warnings.warn(f"Tool detection warning: {e}", RuntimeWarning, stacklevel=2)

        if list(self.target_dir.glob("jest.config.*")):
            return "jest"
        if list(self.target_dir.glob("vitest.config.*")):
            return "vitest"

        # Rust
        if (self.target_dir / "Cargo.toml").exists():
            return "cargo test"

        # Go
        if list(self.target_dir.glob("**/*_test.go")):
            return "go test"

        return None

    def detect_linter(self) -> Optional[str]:
        """Detect linters configured in the project."""
        # Python
        if (self.target_dir / "ruff.toml").exists() or (self.target_dir / ".ruff.toml").exists():
            return "ruff"
        if (self.target_dir / "pyproject.toml").exists():
            try:
                content = (self.target_dir / "pyproject.toml").read_text(encoding="utf-8", errors="ignore")
                if "tool.ruff" in content:
                    return "ruff"
                if "tool.flake8" in content:
                    return "flake8"
            except Exception as e:
                warnings.warn(f"Tool detection warning: {e}", RuntimeWarning, stacklevel=2)
        if (self.target_dir / ".flake8").exists():
            return "flake8"

        # JS / TS
        if list(self.target_dir.glob("eslint.config.*")) or list(self.target_dir.glob(".eslintrc*")):
            return "eslint"
        pkg_json = self.target_dir / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                if "eslint" in deps:
                    return "eslint"
            except Exception as e:
                warnings.warn(f"Tool detection warning: {e}", RuntimeWarning, stacklevel=2)

        # Rust / Go
        if (self.target_dir / "Cargo.toml").exists():
            return "clippy"
        if (self.target_dir / ".golangci.yml").exists() or (self.target_dir / ".golangci.yaml").exists():
            return "golangci-lint"

        return None

    def detect_formatter(self) -> Optional[str]:
        """Detect formatters."""
        if (self.target_dir / ".prettierrc").exists() or list(self.target_dir.glob("prettier.config.*")):
            return "prettier"
        if (self.target_dir / "pyproject.toml").exists():
            try:
                c = (self.target_dir / "pyproject.toml").read_text(encoding="utf-8", errors="ignore")
                if "tool.black" in c:
                    return "black"
                if "tool.ruff" in c:
                    return "ruff"
            except Exception as e:
                warnings.warn(f"Tool detection warning: {e}", RuntimeWarning, stacklevel=2)
        return None

    def detect_type_checker(self) -> Optional[str]:
        """Detect static type checkers."""
        if (self.target_dir / "tsconfig.json").exists():
            return "tsc"
        if (self.target_dir / "mypy.ini").exists() or (self.target_dir / ".mypy.ini").exists():
            return "mypy"
        if (self.target_dir / "pyproject.toml").exists():
            try:
                c = (self.target_dir / "pyproject.toml").read_text(encoding="utf-8", errors="ignore")
                if "tool.pyright" in c:
                    return "pyright"
                if "tool.mypy" in c:
                    return "mypy"
            except Exception as e:
                warnings.warn(f"Tool detection warning: {e}", RuntimeWarning, stacklevel=2)
        return None

    def detect_ci_platform(self) -> Optional[str]:
        """Detect CI/CD configuration."""
        if list(self.target_dir.glob(".github/workflows/*.yml")) or list(self.target_dir.glob(".github/workflows/*.yaml")):
            return "github_actions"
        if (self.target_dir / ".gitlab-ci.yml").exists():
            return "gitlab_ci"
        if (self.target_dir / ".circleci" / "config.yml").exists():
            return "circleci"
        if (self.target_dir / "azure-pipelines.yml").exists():
            return "azure_pipelines"
        return None

    def detect_containerization(self) -> Optional[str]:
        """Detect containerization tooling as a single string value."""
        has_docker = (self.target_dir / "Dockerfile").exists() or (self.target_dir / "Containerfile").exists()
        has_compose = any((self.target_dir / f).exists() for f in ["docker-compose.yml", "docker-compose.yaml", "compose.yaml", "compose.yml"])
        has_k8s = (self.target_dir / "k8s").is_dir() or (self.target_dir / "kubernetes").is_dir() or (self.target_dir / "Chart.yaml").exists()

        parts = []
        if has_docker:
            parts.append("docker")
        if has_compose:
            parts.append("docker-compose")
        if has_k8s:
            parts.append("kubernetes")

        return ",".join(parts) if parts else None

    def detect_iac(self) -> Optional[str]:
        """Detect Infrastructure as Code tooling as a single string value."""
        tools = []
        if list(self.target_dir.glob("*.tf")) or list(self.target_dir.glob("terraform/**/*.tf")):
            tools.append("terraform")
        if (self.target_dir / "Pulumi.yaml").exists() or (self.target_dir / "Pulumi.yml").exists():
            tools.append("pulumi")
        return ",".join(tools) if tools else None

    def detect_monorepo(self) -> Dict[str, Any]:
        """Detect monorepo tooling and structure."""
        is_mono = False
        kind = None
        packages = []

        if (self.target_dir / "pnpm-workspace.yaml").exists():
            is_mono = True
            kind = "pnpm-workspace"
        elif (self.target_dir / "lerna.json").exists():
            is_mono = True
            kind = "lerna"
        elif (self.target_dir / "turbo.json").exists():
            is_mono = True
            kind = "turborepo"
        elif (self.target_dir / "nx.json").exists():
            is_mono = True
            kind = "nx"
        elif (self.target_dir / "go.work").exists():
            is_mono = True
            kind = "go-work"
        elif (self.target_dir / "Cargo.toml").exists():
            try:
                c = (self.target_dir / "Cargo.toml").read_text(encoding="utf-8", errors="ignore")
                if "[workspace]" in c:
                    is_mono = True
                    kind = "cargo-workspace"
            except Exception as e:
                warnings.warn(f"Tool detection warning: {e}", RuntimeWarning, stacklevel=2)

        pkg_dir = self.target_dir / "packages"
        if pkg_dir.is_dir():
            is_mono = True
            packages = [p.name for p in pkg_dir.iterdir() if p.is_dir()]

        return {
            "is_monorepo": is_mono,
            "type": kind,
            "packages": packages
        }

    def detect_build_tool(self) -> Optional[str]:
        """Detect package / build tools."""
        if (self.target_dir / "poetry.lock").exists():
            return "poetry"
        if (self.target_dir / "Pipfile").exists():
            return "pipenv"
        if (self.target_dir / "pnpm-lock.yaml").exists():
            return "pnpm"
        if (self.target_dir / "yarn.lock").exists():
            return "yarn"
        if (self.target_dir / "package-lock.json").exists():
            return "npm"
        if (self.target_dir / "Cargo.lock").exists():
            return "cargo"
        if (self.target_dir / "go.mod").exists():
            return "go"
        return None


"""Tests for AR-7: Railway deployment config and uvicorn startup."""

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


class TestDeploymentConfig:
    """AR-7 AC: App includes Railway deployment config."""

    def test_procfile_exists(self):
        procfile = REPO_ROOT / "Procfile"
        assert procfile.exists(), "Procfile must exist at repo root for Railway deployment"

    def test_procfile_runs_uvicorn(self):
        procfile = REPO_ROOT / "Procfile"
        content = procfile.read_text()
        assert "uvicorn" in content
        assert "autoremind.web:app" in content

    def test_requirements_txt_exists(self):
        requirements = REPO_ROOT / "requirements.txt"
        assert requirements.exists(), "requirements.txt must exist for Railway to install dependencies"

    def test_requirements_includes_key_deps(self):
        requirements = REPO_ROOT / "requirements.txt"
        content = requirements.read_text().lower()
        assert "fastapi" in content
        assert "uvicorn" in content
        assert "twilio" in content
        assert "openpyxl" in content

"""
tests/test_environment_dependencies.py — Regression verification for environment dependencies and encoding.

Verifies:
- requirements.txt is standard UTF-8 without byte order marks (BOM).
- Core production and test dependencies (pyarrow, pytest, pandas, numpy, etc.) are declared.
- Key modules depending on pyarrow (data.market.storage, universe.liquidity) import cleanly.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
REQUIREMENTS_PATH = ROOT_DIR / "requirements.txt"


def test_requirements_encoding_utf8_without_bom():
    """Verify requirements.txt is strictly valid UTF-8 and contains no BOM."""
    assert REQUIREMENTS_PATH.exists(), f"requirements.txt not found at {REQUIREMENTS_PATH}"
    
    with open(REQUIREMENTS_PATH, "rb") as f:
        raw_bytes = f.read()

    # Must not contain UTF-16 or UTF-8 BOM headers
    assert not raw_bytes.startswith(b"\xff\xfe"), "requirements.txt has UTF-16LE BOM (\\xff\\xfe)"
    assert not raw_bytes.startswith(b"\xfe\xff"), "requirements.txt has UTF-16BE BOM (\\xfe\\xff)"
    assert not raw_bytes.startswith(b"\xef\xbb\xbf"), "requirements.txt has UTF-8 BOM (\\xef\\xbb\\xbf)"

    # Must decode cleanly as strict UTF-8
    try:
        decoded_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        raise AssertionError(f"requirements.txt failed to decode as UTF-8: {e}")

    lines = [line.strip() for line in decoded_text.splitlines() if line.strip() and not line.startswith("#")]
    assert len(lines) >= 30, f"Expected at least 30 requirement entries, got {len(lines)}"


def test_core_dependencies_present():
    """Verify that core data/universe dependencies identified in the audit are declared."""
    with open(REQUIREMENTS_PATH, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    declared_packages = set()
    for line in lines:
        pkg_name = re.split(r"[=<>!~]", line)[0].strip().lower().replace("_", "-")
        declared_packages.add(pkg_name)

    # Core dependencies verified in Audit Issue 3
    assert "pyarrow" in declared_packages, "pyarrow missing from requirements.txt"
    assert "pytest" in declared_packages, "pytest missing from requirements.txt"

    # Core quantitative foundation dependencies
    assert "pandas" in declared_packages, "pandas missing from requirements.txt"
    assert "numpy" in declared_packages, "numpy missing from requirements.txt"
    assert "scipy" in declared_packages, "scipy missing from requirements.txt"
    assert "scikit-learn" in declared_packages, "scikit-learn missing from requirements.txt"


def test_no_duplicate_dependencies():
    """Verify that requirements.txt has no duplicate package definitions."""
    with open(REQUIREMENTS_PATH, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    pkg_list = [re.split(r"[=<>!~]", line)[0].strip().lower().replace("_", "-") for line in lines]
    seen = set()
    duplicates = set()
    for pkg in pkg_list:
        if pkg in seen:
            duplicates.add(pkg)
        seen.add(pkg)

    assert not duplicates, f"Duplicate packages found in requirements.txt: {duplicates}"


def test_pyarrow_and_storage_imports():
    """Verify that pyarrow and Parquet storage engine import without missing module errors."""
    import pyarrow
    assert hasattr(pyarrow, "__version__")

    from data.market.storage import ParquetMarketDataStorage
    assert ParquetMarketDataStorage is not None


def test_universe_and_liquidity_imports():
    """Verify that universe liquidity engine and constituent models import cleanly."""
    from universe.liquidity import LiquidityEngine
    from universe.universe_manager import UniverseManager
    from universe.models import Stock, ListingStatus

    assert LiquidityEngine is not None
    assert UniverseManager is not None
    assert ListingStatus is not None

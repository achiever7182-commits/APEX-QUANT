"""
ml/equity/registry.py — Model Artifact and Versioning Registry for Equity ML.

Manages:
  - Serialization of trained models (.joblib)
  - Associated metadata descriptors (.json)
  - Immutable versioning (equity_model_v1, v2, ...) under models/equity/
  - Tracking feature lists, target horizons, training dates, and evaluation metrics
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import joblib

from ml.equity.models import IEquityModel


@dataclass
class ModelArtifactMetadata:
    """Metadata descriptor saved alongside model binary."""
    model_name: str
    version: str
    target_name: str
    target_horizon: int
    features: List[str]
    training_start: str
    training_end: str
    validation_start: Optional[str] = None
    validation_end: Optional[str] = None
    test_start: Optional[str] = None
    test_end: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    random_seed: int = 42
    hyperparameters: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    model_filename: str = ""
    metadata_filename: str = ""


class ModelRegistry:
    """Manages storage and loading of versioned equity models."""

    def __init__(self, base_dir: Optional[Union[str, Path]] = None):
        if base_dir is None:
            # Default to project models/equity/
            root = Path(__file__).resolve().parent.parent.parent
            self.base_dir = root / "models" / "equity"
        else:
            self.base_dir = Path(base_dir)

        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_artifact(
        self,
        model: IEquityModel,
        metadata: ModelArtifactMetadata,
        tag: Optional[str] = None,
    ) -> str:
        """
        Save model object and metadata JSON. Returns version string.
        """
        # Generate version identifier if not set
        if not metadata.version:
            existing = self.list_artifacts()
            v_num = len(existing) + 1
            metadata.version = f"v{v_num}"

        tag_str = f"_{tag}" if tag else ""
        base_name = f"equity_{metadata.version}{tag_str}"
        model_file = f"{base_name}.joblib"
        meta_file = f"{base_name}_meta.json"

        metadata.model_filename = model_file
        metadata.metadata_filename = meta_file

        # Save model
        model_path = self.base_dir / model_file
        joblib.dump(model, model_path)

        # Save JSON metadata
        meta_path = self.base_dir / meta_file
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(asdict(metadata), f, indent=2)

        return metadata.version

    def load_artifact(self, version: str) -> Tuple[IEquityModel, ModelArtifactMetadata]:
        """Load model binary and metadata by version string."""
        meta_candidates = list(self.base_dir.glob(f"equity_{version}*_meta.json"))
        if not meta_candidates:
            raise FileNotFoundError(f"No metadata found for version '{version}' in {self.base_dir}")

        meta_path = meta_candidates[0]
        with open(meta_path, "r", encoding="utf-8") as f:
            meta_dict = json.load(f)

        meta = ModelArtifactMetadata(**meta_dict)
        model_path = self.base_dir / meta.model_filename
        if not model_path.exists():
            raise FileNotFoundError(f"Model file {meta.model_filename} not found.")

        model = joblib.load(model_path)
        return model, meta

    def list_artifacts(self) -> List[Dict[str, Any]]:
        """List all saved model artifacts and summaries."""
        artifacts = []
        for meta_path in sorted(self.base_dir.glob("equity_*_meta.json")):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    artifacts.append(json.load(f))
            except Exception:
                continue
        return artifacts

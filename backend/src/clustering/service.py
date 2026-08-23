"""Loads the fitted model for the API, building it on first use if absent."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from clustering.model import DEFAULT_MODEL_PATH, ClusterAssignment, ClusteringModel
from clustering.pipeline import DEFAULT_REPORT_PATH, build


class ClusteringService:
    """One fitted model shared by every request.

    Loading is deferred and guarded by a lock: fitting takes several seconds,
    and two concurrent first requests should not both pay for it.

        >>> service = ClusteringService()
        >>> service.classify("The band announced a world tour.").category
        'Entertainment'
    """

    def __init__(
        self,
        *,
        model_path: Path = DEFAULT_MODEL_PATH,
        report_path: Path = DEFAULT_REPORT_PATH,
    ) -> None:
        self._model_path = model_path
        self._report_path = report_path
        self._model: ClusteringModel | None = None
        self._report: dict[str, object] | None = None
        self._lock = threading.Lock()

    @property
    def model(self) -> ClusteringModel:
        self._ensure_loaded()
        assert self._model is not None
        return self._model

    @property
    def report(self) -> dict[str, object]:
        self._ensure_loaded()
        assert self._report is not None
        return self._report

    def classify(self, text: str) -> ClusterAssignment:
        return self.model.predict(text)

    def _ensure_loaded(self) -> None:
        if self._model is not None and self._report is not None:
            return
        with self._lock:
            if self._model is not None and self._report is not None:
                return
            if self._model_path.exists() and self._report_path.exists():
                self._model = ClusteringModel.load(self._model_path)
                self._report = json.loads(self._report_path.read_text(encoding="utf-8"))
            else:
                artifacts = build(
                    model_path=self._model_path, report_path=self._report_path
                )
                self._model = artifacts.model
                self._report = artifacts.report

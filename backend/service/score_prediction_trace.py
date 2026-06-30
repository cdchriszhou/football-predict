"""
Score prediction tracking and monitoring module.

Records decision paths and configuration parameters for each prediction,
enabling post-analysis and parameter optimization.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any


class PredictionTrace:
    """Records prediction decision path and parameters."""

    def __init__(self, match_id: str | None = None):
        self.match_id = match_id
        self.timestamp = datetime.utcnow().isoformat()
        self.pipeline_stages: list[dict[str, Any]] = []
        self.final_picks: list[str] = []
        self.final_upset: str | None = None
        self.warnings: list[str] = []
        self.config_snapshot: dict[str, Any] = {}
        self.input_params: dict[str, Any] = {}

    def record_stage(
        self,
        stage_name: str,
        input_scores: list[str],
        output_scores: list[str],
        reason: str | None = None,
        params_used: dict[str, Any] | None = None,
    ) -> None:
        """Record a pipeline stage transformation."""
        self.pipeline_stages.append({
            "stage": stage_name,
            "input": input_scores,
            "output": output_scores,
            "reason": reason,
            "params": params_used or {},
            "timestamp": datetime.utcnow().isoformat(),
        })

    def record_config_snapshot(self, config: dict[str, Any]) -> None:
        """Record configuration values used in this prediction."""
        self.config_snapshot = dict(config)

    def record_input_params(self, params: dict[str, Any]) -> None:
        """Record input parameters (W/D/L rates, XG, etc)."""
        self.input_params = dict(params)

    def record_final_result(
        self,
        picks: list[str],
        upset: str | None,
        warnings: list[str] | None = None,
    ) -> None:
        """Record final prediction result."""
        self.final_picks = list(picks)
        self.final_upset = upset
        self.warnings = list(warnings or [])

    def to_dict(self) -> dict[str, Any]:
        """Convert trace to dictionary for serialization."""
        return {
            "match_id": self.match_id,
            "timestamp": self.timestamp,
            "input_params": self.input_params,
            "config_snapshot": self.config_snapshot,
            "pipeline_stages": self.pipeline_stages,
            "final_picks": self.final_picks,
            "final_upset": self.final_upset,
            "warnings": self.warnings,
        }

    def to_json(self) -> str:
        """Convert trace to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            f"Prediction Trace: {self.match_id or 'unknown'}",
            f"Timestamp: {self.timestamp}",
            f"Input: W={self.input_params.get('win_rate')}% D={self.input_params.get('draw_rate')}% L={self.input_params.get('lose_rate')}%",
            f"Pipeline stages ({len(self.pipeline_stages)}):",
        ]
        for stage in self.pipeline_stages:
            lines.append(
                f"  - {stage['stage']}: {stage['input']} → {stage['output']} ({stage['reason'] or 'default'})"
            )
        lines.extend([
            f"Final picks: {self.final_picks}",
            f"Final upset: {self.final_upset}",
            f"Warnings: {len(self.warnings)}",
        ])
        if self.warnings:
            for w in self.warnings:
                lines.append(f"  - {w}")
        return "\n".join(lines)


class PredictionTracker:
    """Global tracker for prediction traces."""

    _instance: PredictionTracker | None = None
    _traces: list[PredictionTrace] = []

    def __new__(cls) -> PredictionTracker:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def start_trace(cls, match_id: str | None = None) -> PredictionTrace:
        """Start a new prediction trace."""
        trace = PredictionTrace(match_id)
        cls._traces.append(trace)
        return trace

    @classmethod
    def get_recent_traces(cls, limit: int = 100) -> list[PredictionTrace]:
        """Get recent prediction traces."""
        return cls._traces[-limit:]

    @classmethod
    def clear_traces(cls) -> None:
        """Clear all stored traces."""
        cls._traces = []

    @classmethod
    def export_traces(cls, filepath: str) -> None:
        """Export all traces to JSON file."""
        data = [t.to_dict() for t in cls._traces]
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def analyze_parameter_usage(cls) -> dict[str, Any]:
        """Analyze which configuration parameters were actually used."""
        param_counts: dict[str, int] = {}
        for trace in cls._traces:
            for stage in trace.pipeline_stages:
                for param in stage.get("params", {}):
                    param_counts[param] = param_counts.get(param, 0) + 1
        return {
            "total_traces": len(cls._traces),
            "parameter_usage": param_counts,
            "most_used": sorted(param_counts.items(), key=lambda x: -x[1])[:10],
        }


def create_trace_decorator(stage_name: str):
    """Decorator to automatically record pipeline stage transformations."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Extract input scores from args
            input_scores = []
            if args and isinstance(args[0], list):
                input_scores = list(args[0])

            # Execute function
            result = func(*args, **kwargs)

            # Extract output scores
            output_scores = list(result) if isinstance(result, list) else []

            # Record trace if tracker has active trace
            recent = PredictionTracker.get_recent_traces(1)
            if recent:
                trace = recent[0]
                trace.record_stage(
                    stage_name=stage_name,
                    input_scores=input_scores,
                    output_scores=output_scores,
                    reason=kwargs.get("reason"),
                )

            return result
        return wrapper
    return decorator
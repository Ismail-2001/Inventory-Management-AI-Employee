"""Lightweight Prometheus-compatible metrics collector.

No external dependencies — emits Prometheus text format from in-process counters/histograms.
"""
from collections import defaultdict
from threading import Lock
from typing import Any

from fastapi import FastAPI


class _Metrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._histogram_bounds: list[float] = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]

    def inc(self, name: str, value: float = 1.0, **labels: str) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] += value

    def gauge(self, name: str, value: float, **labels: str) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._gauges[key] = value

    def observe(self, name: str, value: float, **labels: str) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._histograms[key].append(value)

    def _key(self, name: str, labels: dict[str, str]) -> str:
        if labels:
            label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
            return f"{name}{{{label_str}}}"
        return name

    def render(self) -> str:
        lines: list[str] = []
        with self._lock:
            for key, val in sorted(self._counters.items()):
                lines.append(f"# TYPE {key.split('{')[0]} counter")
                lines.append(f"{key} {val}")
            for key, val in sorted(self._gauges.items()):
                lines.append(f"# TYPE {key.split('{')[0]} gauge")
                lines.append(f"{key} {val}")
            for key, vals in sorted(self._histograms.items()):
                name, _, label_str = key.partition("{")
                inner = label_str[:-1] if label_str else ""
                labels = f"{inner}," if inner else ""
                lines.append(f"# TYPE {name} histogram")
                cumulative = 0
                for bound in self._histogram_bounds:
                    cumulative += sum(1 for v in vals if v <= bound)
                    lines.append(f'{name}_bucket{{{labels}le="{bound}"}} {cumulative}')
                cumulative += sum(1 for v in vals if v > self._histogram_bounds[-1])
                lines.append(f'{name}_bucket{{{labels}le="+Inf"}} {cumulative}')
                if inner:
                    lines.append(f"{name}_sum{{{inner}}} {sum(vals)}")
                    lines.append(f"{name}_count{{{inner}}} {len(vals)}")
                else:
                    lines.append(f"{name}_sum {sum(vals)}")
                    lines.append(f"{name}_count {len(vals)}")
        lines.append("")
        return "\n".join(lines)


metrics = _Metrics()


def setup_metrics(app: FastAPI) -> None:
    @app.get("/metrics")
    async def prometheus_metrics() -> Any:
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")

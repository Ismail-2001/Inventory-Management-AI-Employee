"""Lightweight Prometheus-compatible metrics collector.

No external dependencies — emits Prometheus text format from in-process counters/histograms.
"""
import time
from collections import defaultdict
from threading import Lock


class _Metrics:
    def __init__(self):
        self._lock = Lock()
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._histogram_bounds = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]

    def inc(self, name: str, value: float = 1.0, **labels):
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] += value

    def gauge(self, name: str, value: float, **labels):
        key = self._key(name, labels)
        with self._lock:
            self._gauges[key] = value

    def observe(self, name: str, value: float, **labels):
        key = self._key(name, labels)
        with self._lock:
            self._histograms[key].append(value)

    def _key(self, name: str, labels: dict) -> str:
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
                base = key.split("{")[0]
                lines.append(f"# TYPE {base} histogram")
                cumulative = 0
                for bound in self._histogram_bounds:
                    cumulative += sum(1 for v in vals if v <= bound)
                    lines.append(f'{key}_bucket{{le="{bound}"}} {cumulative}')
                cumulative += sum(1 for v in vals if v > self._histogram_bounds[-1])
                lines.append(f'{key}_bucket{{le="+Inf"}} {cumulative}')
                lines.append(f"{key}_sum {sum(vals)}")
                lines.append(f"{key}_count {len(vals)}")
        lines.append("")
        return "\n".join(lines)


metrics = _Metrics()


def setup_metrics(app):
    @app.get("/metrics")
    async def prometheus_metrics():
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")

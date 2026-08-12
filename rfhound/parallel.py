"""Small multithreading helper for running independent I/O-bound jobs at once.

RFHound spends most of its wall-clock time waiting on external processes
(hackrf_sweep, iw, btmgmt, tool probes). Those calls are independent, so running
them on a thread pool turns a sum of latencies into a max. This module wraps
``concurrent.futures.ThreadPoolExecutor`` with per-job exception isolation: one
job blowing up never takes down the batch — you get its error back as a result.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class JobResult:
    name: str
    ok: bool
    value: Any = None
    error: str = ""


def run_jobs(jobs: dict[str, Callable[[], Any]], *, workers: int = 4,
             timeout: float | None = None) -> dict[str, JobResult]:
    """Run ``{name: callable}`` concurrently; return ``{name: JobResult}``.

    Each callable takes no arguments. Exceptions are captured per job (never
    propagated), so the caller always gets a result for every name. ``workers``
    is clamped to at least 1 and at most the number of jobs.
    """
    if not jobs:
        return {}
    workers = max(1, min(int(workers), len(jobs)))
    results: dict[str, JobResult] = {}
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="rfhound") as ex:
        futures = {ex.submit(fn): name for name, fn in jobs.items()}
        for fut in as_completed(futures, timeout=timeout):
            name = futures[fut]
            try:
                results[name] = JobResult(name, True, fut.result())
            except Exception as exc:  # noqa: BLE001 — isolation is the whole point
                results[name] = JobResult(name, False, None, f"{type(exc).__name__}: {exc}")
    return results

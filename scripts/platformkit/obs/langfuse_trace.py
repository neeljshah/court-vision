"""
langfuse_trace.py -- minimal optional Langfuse tracing + structured-output guardrail.

Import guard: if langfuse is not installed or LANGFUSE_SECRET_KEY is absent,
all trace calls are silent no-ops. The system never crashes due to missing observability.

Usage:
  from scripts.platformkit.obs.langfuse_trace import tracer, validate_output

  with tracer.span("eval_gate", metadata={"sport": "nba"}) as span:
      result = run_eval(...)
      validated = validate_output(result, EVAL_SCHEMA, span=span)

Structured-output guardrail:
  validate_output(data, schema_dict) raises ValueError on first violation.
  Retry wrapper retries the producer callable up to max_retries times.
"""
import json
import os
import time
import contextlib
from typing import Any, Callable, Dict, Optional

# ---------------------------------------------------------------------------
# Langfuse availability guard
# ---------------------------------------------------------------------------
_LANGFUSE_ENABLED = False
_lf_client = None

try:
    if os.environ.get("LANGFUSE_SECRET_KEY"):
        from langfuse import Langfuse  # type: ignore
        _lf_client = Langfuse(
            secret_key=os.environ["LANGFUSE_SECRET_KEY"],
            public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
            host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
        _LANGFUSE_ENABLED = True
except Exception:
    pass  # langfuse absent or misconfigured -- stay silent


# ---------------------------------------------------------------------------
# No-op span context manager (used when Langfuse is absent)
# ---------------------------------------------------------------------------
class _NoopSpan:
    def __init__(self):
        self.trace_id = None

    def update(self, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


# ---------------------------------------------------------------------------
# Tracer facade
# ---------------------------------------------------------------------------
class Tracer:
    """Thin facade over Langfuse. All methods are no-ops if Langfuse is absent."""

    def enabled(self) -> bool:
        return _LANGFUSE_ENABLED

    @contextlib.contextmanager
    def span(self, name: str, metadata: Optional[Dict] = None, input_data: Any = None):
        if not _LANGFUSE_ENABLED or _lf_client is None:
            yield _NoopSpan()
            return

        trace = _lf_client.trace(name=name, metadata=metadata or {}, input=input_data)
        span = trace.span(name=name, start_time=time.time())
        try:
            yield span
        except Exception as exc:
            span.update(output={"error": str(exc)}, level="ERROR")
            raise
        finally:
            span.update(end_time=time.time())
            _lf_client.flush()

    def log_generation(
        self,
        name: str,
        model: str,
        prompt: str,
        completion: str,
        cost_usd: float = 0.0,
        metadata: Optional[Dict] = None,
    ) -> None:
        if not _LANGFUSE_ENABLED or _lf_client is None:
            return
        try:
            _lf_client.generation(
                name=name,
                model=model,
                prompt=prompt,
                completion=completion,
                usage={"total_cost": cost_usd},
                metadata=metadata or {},
            )
            _lf_client.flush()
        except Exception:
            pass


tracer = Tracer()


# ---------------------------------------------------------------------------
# Structured-output guardrail
# ---------------------------------------------------------------------------
def _check_schema(data: Any, schema: Dict, path: str = "root") -> None:
    """
    Minimal schema validator supporting: type, required, properties, items.
    Raises ValueError describing the first violation found.
    """
    dtype = schema.get("type")
    if dtype == "object":
        if not isinstance(data, dict):
            raise ValueError(f"{path}: expected object, got {type(data).__name__}")
        for key in schema.get("required", []):
            if key not in data:
                raise ValueError(f"{path}: missing required key '{key}'")
        for prop, sub_schema in schema.get("properties", {}).items():
            if prop in data:
                _check_schema(data[prop], sub_schema, path=f"{path}.{prop}")
    elif dtype == "array":
        if not isinstance(data, list):
            raise ValueError(f"{path}: expected array, got {type(data).__name__}")
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(data):
                _check_schema(item, item_schema, path=f"{path}[{i}]")
    elif dtype == "number":
        if not isinstance(data, (int, float)):
            raise ValueError(f"{path}: expected number, got {type(data).__name__}")
    elif dtype == "string":
        if not isinstance(data, str):
            raise ValueError(f"{path}: expected string, got {type(data).__name__}")
    elif dtype == "boolean":
        if not isinstance(data, bool):
            raise ValueError(f"{path}: expected boolean, got {type(data).__name__}")


def validate_output(
    data: Any,
    schema: Dict,
    span: Optional[Any] = None,
) -> Any:
    """Validate data against schema. Attaches error to span if provided. Returns data."""
    try:
        _check_schema(data, schema)
    except ValueError as exc:
        if span is not None:
            try:
                span.update(output={"schema_error": str(exc)}, level="WARNING")
            except Exception:
                pass
        raise
    return data


def retry_with_validation(
    producer: Callable[[], Any],
    schema: Dict,
    max_retries: int = 3,
    span: Optional[Any] = None,
) -> Any:
    """
    Call producer() up to max_retries times until validate_output passes.
    Raises last ValueError if all attempts fail.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            result = producer()
            return validate_output(result, schema, span=span)
        except ValueError as exc:
            last_exc = exc
            if span is not None:
                try:
                    span.update(
                        metadata={"retry_attempt": attempt, "error": str(exc)}
                    )
                except Exception:
                    pass
    raise ValueError(
        f"retry_with_validation: all {max_retries} attempts failed. "
        f"Last error: {last_exc}"
    )

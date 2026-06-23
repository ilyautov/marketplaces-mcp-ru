"""Safety gating for write/destructive operations.

Marketplace API keys grant power over prices, stocks and money. A misfired
write can drop a price 3x or zero out stock. We gate mutations locally, before
the request leaves the machine.

Levels:
- read        : no confirmation needed
- write       : requires confirm_write=True
- destructive : requires confirm_write=True AND i_understand_this_modifies_data=True
"""
from __future__ import annotations

from typing import Optional

from .errors import make_error

SAFETY_LEVELS = ("read", "write", "destructive")

# Heuristic: infer safety from HTTP verb when the catalog does not state it.
_VERB_DEFAULT = {
    "GET": "read",
    "HEAD": "read",
    "POST": "write",   # most marketplace POSTs are reads-with-body OR writes; catalog overrides
    "PUT": "write",
    "PATCH": "write",
    "DELETE": "destructive",
}


def infer_safety(method: str, declared: Optional[str]) -> str:
    """Return the safety level, preferring the catalog's declared value."""
    if declared in SAFETY_LEVELS:
        return declared  # type: ignore[return-value]
    return _VERB_DEFAULT.get(method.upper(), "write")


def check_gate(
    safety: str,
    *,
    confirm_write: bool,
    i_understand_this_modifies_data: bool,
    operation_id: Optional[str] = None,
    endpoint: Optional[str] = None,
) -> Optional[dict]:
    """Return an error envelope if the gate is NOT satisfied, else None.

    The returned envelope has http_call_skipped semantics: nothing was sent.
    """
    if safety == "read":
        return None

    if safety == "write" and not confirm_write:
        return make_error(
            "safety_gate",
            f"This is a WRITE operation ({operation_id or endpoint}). "
            "Pass confirm_write=true to proceed. Nothing was sent.",
            operation_id=operation_id,
            endpoint=endpoint,
            retryable=False,
            details={"required": ["confirm_write=true"], "http_call_skipped": True},
        )

    if safety == "destructive":
        missing = []
        if not confirm_write:
            missing.append("confirm_write=true")
        if not i_understand_this_modifies_data:
            missing.append("i_understand_this_modifies_data=true")
        if missing:
            return make_error(
                "safety_gate",
                f"This is a DESTRUCTIVE operation ({operation_id or endpoint}) that "
                "deletes or irreversibly changes data. Both confirmations are required. "
                "Nothing was sent.",
                operation_id=operation_id,
                endpoint=endpoint,
                retryable=False,
                details={"required": missing, "http_call_skipped": True},
            )
    return None

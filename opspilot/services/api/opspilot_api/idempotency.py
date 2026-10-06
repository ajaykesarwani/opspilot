import hashlib
import json

from opspilot_contracts import OperationalRequestCreate


def payload_fingerprint(payload: OperationalRequestCreate) -> str:
    """Stable hash of the validated payload, so an omitted default and an explicit one match."""
    canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()

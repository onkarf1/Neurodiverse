"""Values shared by more than one module.

A value used in only one module stays in that module. Configurable values belong in
config.py as settings, not here.
"""

from typing import Final

API_V1_PREFIX: Final = "/v1"

REQUEST_ID_HEADER: Final = "X-Request-ID"
PROBLEM_JSON: Final = "application/problem+json"

ACCESS_LOGGER: Final = "app.access"
ERROR_LOGGER: Final = "app.error"

# Longest password login accepts; also enforced when accounts are created, so no account can
# have a password that login would refuse. The cap bounds hashing work per request.
MAX_PASSWORD_LENGTH: Final = 128

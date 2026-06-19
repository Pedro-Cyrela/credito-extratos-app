from __future__ import annotations

from collections.abc import MutableMapping

HOLDER_FIRST_NAME_DEFAULT = False


def initialize_holder_first_name(session_state: MutableMapping[str, object]) -> None:
    session_state.setdefault("include_holder_first_name", HOLDER_FIRST_NAME_DEFAULT)

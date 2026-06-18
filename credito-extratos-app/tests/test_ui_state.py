from src.ui_state import HOLDER_FIRST_NAME_DEFAULT, initialize_holder_first_name


def test_holder_first_name_starts_disabled():
    session_state = {}

    initialize_holder_first_name(session_state)

    assert HOLDER_FIRST_NAME_DEFAULT is False
    assert session_state["include_holder_first_name"] is False


def test_holder_first_name_preserves_user_choice_during_session():
    session_state = {"include_holder_first_name": True}

    initialize_holder_first_name(session_state)

    assert session_state["include_holder_first_name"] is True


def test_holder_first_name_returns_to_disabled_after_session_clear():
    session_state = {"include_holder_first_name": True}
    session_state.pop("include_holder_first_name")

    initialize_holder_first_name(session_state)

    assert session_state["include_holder_first_name"] is False

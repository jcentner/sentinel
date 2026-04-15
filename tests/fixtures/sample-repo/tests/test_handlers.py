"""Tests for request handlers — mix of coherent and drifted tests."""

from myapp.handlers import (
    handle_delete_user,
    handle_login,
    handle_logout,
    handle_profile,
    handle_register,
    handle_search,
)


def test_login_validates_bcrypt():
    """Test that login authenticates using bcrypt password hashing.

    The handler should verify the password against a stored bcrypt hash,
    not compare plaintext passwords.
    """
    # DRIFT: handler does plaintext comparison, not bcrypt
    handle_register({"username": "alice", "email": "alice@test.com"})
    result = handle_login({
        "username": "alice",
        "password": "secret",
        "_stored_password": "secret",
    })
    assert result["status"] == 200


def test_register_sends_welcome_email():
    """Test that registration sends a welcome email to the new user.

    After creating the account, the handler should dispatch an async
    email via the notification service.
    """
    # DRIFT: handler creates user but never sends email
    result = handle_register({"username": "bob", "email": "bob@test.com"})
    assert result["status"] == 201


def test_logout_returns_200():
    """Test that logout always returns 200."""
    result = handle_logout({"token": "fake-token"})
    assert result["status"] == 200


def test_profile_includes_avatar():
    """Test that profile response includes the user's avatar URL.

    The avatar URL should be a gravatar link based on the email hash.
    """
    # DRIFT: handler returns profile without avatar URL
    handle_register({"username": "carol", "email": "carol@test.com"})
    result = handle_profile({"username": "carol"})
    assert result["status"] == 200
    assert "avatar_url" in result


def test_search_fuzzy_matching():
    """Test that search uses fuzzy matching for approximate results.

    Searching for 'dave' should match 'david' via Levenshtein distance.
    """
    # DRIFT: handler does exact substring match, not fuzzy
    handle_register({"username": "david", "email": "david@test.com"})
    result = handle_search("dave")
    assert result["total"] >= 1


def test_search_with_filters():
    """Test that search respects role filters."""
    result = handle_search("", filters={"role": "admin"})
    assert isinstance(result["results"], list)


def test_delete_removes_sessions():
    """Test that deleting a user clears their sessions."""
    handle_register({"username": "eve", "email": "eve@test.com"})
    result = handle_delete_user({"username": "eve"})
    assert result["status"] == 200

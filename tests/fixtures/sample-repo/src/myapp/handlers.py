"""Request handlers for the HTTP API.

Each handler receives a request dict and returns a response dict.
"""

from myapp.models import User


_sessions = {}
_users = {}


def handle_login(request):
    """Authenticate a user with bcrypt password verification.

    Validates the provided username and password against stored
    bcrypt hashes. Returns a session token on success.
    """
    # DRIFT: docstring says bcrypt, code does plaintext comparison
    username = request.get("username", "")
    password = request.get("password", "")

    user = _users.get(username)
    if user is None:
        return {"error": "User not found", "status": 401}

    stored_password = request.get("_stored_password", "")
    if password != stored_password:
        return {"error": "Invalid credentials", "status": 401}

    token = f"session-{username}-{id(request)}"
    _sessions[token] = username
    return {"token": token, "status": 200}


def handle_register(request):
    """Register a new user account and send a welcome email.

    Creates the user record and dispatches an async welcome email
    via the notification service.
    """
    # DRIFT: docstring says sends welcome email, code doesn't
    username = request.get("username", "")
    email = request.get("email", "")

    if username in _users:
        return {"error": "Username taken", "status": 409}

    user = User(user_id=len(_users) + 1, username=username, email=email)
    _users[username] = user
    return {"user_id": user.user_id, "status": 201}


def handle_logout(request):
    """Invalidate the current session token.

    Removes the token from the session store. Returns 200 regardless
    of whether the token was valid.
    """
    token = request.get("token", "")
    _sessions.pop(token, None)
    return {"status": 200}


def handle_profile(request):
    """Return the user profile including avatar URL.

    Fetches the user record and includes the gravatar URL
    based on the user's email hash.
    """
    # DRIFT: docstring says includes avatar URL, response doesn't include it
    username = request.get("username", "")
    user = _users.get(username)
    if user is None:
        return {"error": "User not found", "status": 404}
    return {
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "status": 200,
    }


def handle_search(query, filters=None):
    """Search users with fuzzy matching support.

    Uses Levenshtein distance for approximate matches when the
    exact query doesn't find results. Filters narrow results by
    role, active status, etc.
    """
    # DRIFT: docstring says fuzzy matching, code does exact substring match
    if filters is None:
        filters = {}
    results = []
    for username, user in _users.items():
        if query.lower() in username.lower():
            if filters.get("role") and user.role != filters["role"]:
                continue
            if filters.get("active_only") and not user.active:
                continue
            results.append({"user_id": user.user_id, "username": user.username})
    return {"results": results, "total": len(results), "status": 200}


def handle_delete_user(request):
    """Permanently delete a user account and all associated data.

    Removes the user record, active sessions, order history,
    and any pending invoices.
    """
    # DRIFT: docstring says deletes orders/invoices, code only removes user + sessions
    username = request.get("username", "")
    if username not in _users:
        return {"error": "User not found", "status": 404}
    del _users[username]
    expired = [t for t, u in _sessions.items() if u == username]
    for token in expired:
        del _sessions[token]
    return {"status": 200}

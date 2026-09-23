# One user must never reach another user's rows, graph threads or learning state.
import pytest
from auth.errors import UnauthorizedError
from auth.user_context import new_thread_id, owns_thread, require_thread_owner
from graph.state import create_initial_state
# Two users, each with one study session.
@pytest.fixture
def two_users(users, sessions_repo):
    ada = users.upsert_from_google("google-1", "ada@example.com", "Ada")
    grace = users.upsert_from_google("google-2", "grace@example.com", "Grace")
    ada_session = sessions_repo.create(ada.id, new_thread_id(ada.id), "Recursion")
    grace_session = sessions_repo.create(grace.id, new_thread_id(grace.id), "Embeddings")
    return ada, grace, ada_session, grace_session
# Listing only ever returns your own sessions.
def test_listing_is_scoped_to_the_user(sessions_repo, two_users):
    ada, grace, ada_session, grace_session = two_users
    assert [s.id for s in sessions_repo.list_for_user(ada.id)] == [ada_session.id]
    assert [s.id for s in sessions_repo.list_for_user(grace.id)] == [grace_session.id]
# Fetching someone else's session by id returns nothing, even though the id is valid.
def test_cannot_read_another_users_session(sessions_repo, two_users):
    ada, grace, ada_session, grace_session = two_users
    assert sessions_repo.get(ada.id, grace_session.id) is None
    assert sessions_repo.get(grace.id, ada_session.id) is None
    assert sessions_repo.get(ada.id, ada_session.id) is not None
# Fetching someone else's session by graph thread returns nothing.
def test_cannot_read_another_users_thread(sessions_repo, two_users):
    ada, grace, ada_session, grace_session = two_users
    assert sessions_repo.get_by_thread(ada.id, grace_session.thread_id) is None
    assert sessions_repo.get_by_thread(ada.id, ada_session.thread_id) is not None
# Writing to someone else's session is refused.
def test_cannot_write_to_another_users_session(sessions_repo, two_users):
    ada, grace, ada_session, grace_session = two_users
    with pytest.raises(UnauthorizedError):
        sessions_repo.update_progress(ada.id, grace_session.thread_id, "finished", 100.0, 1)
    assert sessions_repo.get_by_thread(grace.id, grace_session.thread_id).status == "active"
# Deleting someone else's session does nothing and reports that nothing happened.
def test_cannot_delete_another_users_session(sessions_repo, two_users):
    ada, grace, ada_session, grace_session = two_users
    assert sessions_repo.delete(ada.id, grace_session.id) is False
    assert sessions_repo.get(grace.id, grace_session.id) is not None
    assert sessions_repo.delete(grace.id, grace_session.id) is True
# Summaries count only the signed-in user's rows.
def test_summary_counts_only_your_own_rows(connection, sessions_repo, two_users):
    from db.repository import user_learning_summary
    ada, grace, ada_session, _ = two_users
    sessions_repo.update_progress(ada.id, ada_session.thread_id, "finished", 80.0, 2)
    assert user_learning_summary(connection, ada.id) == {
        "sessions": 1,
        "average_score": 80.0,
        "quiz_attempts": 2,
    }
    assert user_learning_summary(connection, grace.id)["average_score"] is None
# Graph threads live in a per-user namespace, so one user's thread id fails another's check.
def test_graph_threads_are_namespaced_per_user():
    ada_thread = new_thread_id("user-1")
    assert owns_thread("user-1", ada_thread) is True
    assert owns_thread("user-2", ada_thread) is False
    assert owns_thread("", ada_thread) is False
    assert owns_thread("user-1", None) is False
    assert require_thread_owner("user-1", ada_thread) == ada_thread
    with pytest.raises(UnauthorizedError):
        require_thread_owner("user-2", ada_thread)
# A guessed thread id from another namespace is rejected, not silently accepted.
def test_forged_thread_id_is_rejected():
    with pytest.raises(UnauthorizedError):
        require_thread_owner("user-1", "user-2::deadbeef")
    with pytest.raises(UnauthorizedError):
        require_thread_owner("user-1", "user-1-extra::deadbeef")
# Starting a session without a signed-in user is impossible.
def test_thread_requires_a_user():
    with pytest.raises(UnauthorizedError):
        new_thread_id("")
# The learning state the graph receives is stamped with the user it belongs to.
def test_graph_state_carries_the_user(users):
    user = users.upsert_from_google("google-1", "ada@example.com", "Ada Lovelace")
    from auth.user_context import UserContext
    context = UserContext.from_user(user)
    state = create_initial_state("Recursion", context.for_graph())
    assert state["user_id"] == user.id
    assert state["user_email"] == "ada@example.com"
    assert state["topic"] == "Recursion"
    assert state["attempts"] == []
# The graph context passed to nodes contains no tokens or secrets.
def test_graph_context_has_no_tokens(users):
    from auth.user_context import UserContext
    user = users.upsert_from_google("google-1", "ada@example.com", "Ada")
    context = UserContext.from_user(user)
    assert set(context.for_graph()) == {"user_id", "user_name", "user_email"}

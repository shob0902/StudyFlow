# Ties the layers together: verified Google profile -> user record -> user context -> login session.
from auth.config import OAuthConfig
from auth.google_oauth import GoogleProfile, PendingLoginStore, complete_login
from auth.session import AuthSession, SessionStore
from auth.user_context import UserContext
from db.database import get_connection
from db.repository import UserRepository
from utils.helpers import log_step
# Create or refresh the user record for a verified Google profile and return its context.
def user_context_for_profile(profile: GoogleProfile) -> UserContext:
    connection = get_connection()
    try:
        repository = UserRepository(connection)
        user = repository.upsert_from_google(
            google_id=profile.google_id,
            email=profile.email,
            name=profile.name,
            profile_picture=profile.picture,
        )
    finally:
        connection.close()
    return UserContext.from_user(user)
# Full login: verify the callback with Google, resolve the user record, then open a session.
def login_with_google(
    config: OAuthConfig,
    pending: PendingLoginStore,
    sessions: SessionStore,
    code: str,
    state: str,
) -> AuthSession:
    profile = complete_login(config, pending, code, state)
    user = user_context_for_profile(profile)
    session = sessions.create(user)
    log_step("AUTH", f"Signed in as {user.email} (user_id={user.user_id})")
    return session
# End a session server-side.
def logout(sessions: SessionStore, session_id: str | None) -> None:
    sessions.revoke(session_id)
# Load the signed-in user's stored learning data, ready for the sidebar and future features.
def load_user_learning_data(user: UserContext) -> dict:
    from db.service import learning_summary, recent_sessions
    return {
        "recent_sessions": recent_sessions(user.user_id, limit=10),
        "summary": learning_summary(user.user_id),
    }

# The authenticated user context handed to the persistence and LangGraph layers.
import uuid
from dataclasses import dataclass
from typing import Any
from auth.errors import UnauthorizedError
from db.models import User
THREAD_SEPARATOR = "::"
# Who the current request is for. Built only from a verified Google sign-in, never from user input.
@dataclass(frozen=True)
class UserContext:
    user_id: str
    google_id: str
    email: str
    name: str
    profile_picture: str = ""
    # Build the context from a stored user record.
    @classmethod
    def from_user(cls, user: User) -> "UserContext":
        return cls(
            user_id=user.id,
            google_id=user.google_id,
            email=user.email,
            name=user.name,
            profile_picture=user.profile_picture,
        )
    # The first name, or the whole name if there is only one word.
    @property
    def first_name(self) -> str:
        return self.name.split(" ")[0] if self.name else self.email.split("@")[0]
    # What the LangGraph layer receives: an identifier plus display fields, and no tokens.
    def for_graph(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "user_name": self.name,
            "user_email": self.email,
        }
# Build a graph thread id inside this user's namespace.
def new_thread_id(user_id: str) -> str:
    if not user_id:
        raise UnauthorizedError("You need to sign in before starting a study session.")
    return f"{user_id}{THREAD_SEPARATOR}{uuid.uuid4()}"
# True when the thread id belongs to this user's namespace.
def owns_thread(user_id: str, thread_id: str | None) -> bool:
    if not user_id or not thread_id:
        return False
    return thread_id.startswith(f"{user_id}{THREAD_SEPARATOR}")
# Raise unless the signed-in user owns this graph thread.
def require_thread_owner(user_id: str, thread_id: str | None) -> str:
    if not owns_thread(user_id, thread_id):
        raise UnauthorizedError("That study session does not belong to your account.")
    return str(thread_id)

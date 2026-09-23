# Authentication errors, all user-friendly and all subclasses of StudyAssistantError.
from utils.helpers import StudyAssistantError
class AuthError(StudyAssistantError):
    pass
class AuthConfigError(AuthError):
    pass
class OAuthCallbackError(AuthError):
    pass
class AccessDeniedError(AuthError):
    pass
class SessionExpiredError(AuthError):
    pass
class UnauthorizedError(AuthError):
    pass
class DatabaseError(StudyAssistantError):
    pass

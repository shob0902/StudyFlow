# Login screen and signed-in user badge. Renders identity only, never tokens.
from auth.config import CLIENT_ID_VAR, CLIENT_SECRET_VAR, REDIRECT_URI_VAR
from auth.user_context import UserContext
from ui.cards import brand, esc
# Landing page shown to visitors who are not signed in yet.
def login_page(auth_url: str) -> str:
    return (
        "<div class='sa-login'>"
        f"{brand()}"
        "<div class='sa-title'>Learn anything, faster.</div>"
        "<p class='tag'>Your personalized AI learning companion.</p>"
        "<div class='panel'>"
        f"<a class='sa-google-btn' href='{esc(auth_url)}' target='_self' rel='noopener'>"
        "<span class='g'>G</span>Continue with Google</a>"
        "<div class='perms'>"
        "<span class='sa-chip'>Your name</span>"
        "<span class='sa-chip'>Your email</span>"
        "<span class='sa-chip'>Your profile picture</span>"
        "</div>"
        "<p class='note'>We only ask Google for your basic profile, so your progress stays tied to your account. "
        "No posting, no contacts, no Drive access.</p>"
        "</div></div>"
    )
# Landing page shown when the Google credentials are not configured on this server.
def login_setup_needed(missing: list[str]) -> str:
    variables = ", ".join(missing) or CLIENT_ID_VAR
    return (
        "<div class='sa-login'>"
        f"{brand()}"
        "<span class='sa-badge'>SETUP NEEDED</span>"
        "<div class='sa-title'>StudyFlow</div>"
        "<p class='tag'>Your personalized AI learning companion.</p>"
        "<div class='panel' style='text-align:left'>"
        "<h4 style='margin:.2rem 0 .6rem;color:var(--primary)'>Google sign-in is not configured</h4>"
        f"<p style='margin:0 0 .6rem'>This server is missing: <b>{esc(variables)}</b></p>"
        "<p style='margin:0 0 .4rem'>Create an OAuth client in the Google Cloud Console, then set "
        f"<code>{esc(CLIENT_ID_VAR)}</code> (and <code>{esc(REDIRECT_URI_VAR)}</code> if the app is not on "
        "localhost) in your <code>.env</code> file and restart the app.</p>"
        f"<p class='note' style='margin:0'>A client secret is optional: set <code>{esc(CLIENT_SECRET_VAR)}</code> "
        "only if your OAuth client was issued one.</p>"
        "<p class='note' style='margin-top:.8rem'>See the Google OAuth section of the README for the full steps.</p>"
        "</div></div>"
    )
# Small identity card for the sidebar: picture, name and email.
# `picture` is the inlined data URI from auth.avatar; initials are shown when there is none.
def user_badge(user: UserContext, picture: str = "") -> str:
    if picture:
        avatar = f"<img src='{esc(picture)}' alt=''>"
    else:
        initial = esc((user.name or user.email)[:1].upper())
        avatar = f"<div class='avatar'>{initial}</div>"
    return (
        "<div class='sa-user'>"
        f"{avatar}"
        "<div class='who'>"
        f"<div class='n'>Welcome, {esc(user.first_name)}</div>"
        f"<div class='e'>{esc(user.email)}</div>"
        "</div></div>"
    )
# Rows summarising the user's saved learning data.
def learning_summary(summary: dict) -> str:
    average = summary.get("average_score")
    rows = [
        ("Topics studied", str(summary.get("sessions", 0))),
        ("Quiz attempts", str(summary.get("quiz_attempts", 0))),
        ("Average score", f"{average:.0f}%" if average is not None else "—"),
    ]
    return "<div class='sa-card' style='padding:.7rem 1rem;margin:.2rem 0 .6rem'>" + "".join(
        f"<div class='sa-side-row'><span>{esc(label)}</span><span>{esc(value)}</span></div>"
        for label, value in rows
    ) + "</div>"

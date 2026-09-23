# Study plans: the history of every plan made, deleting one or all of them, what the dashboard
# says to study now, and where the app opens after signing in.
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import pytest
AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
APP_FILE = str(Path(__file__).resolve().parents[1] / "app.py")
# A signed-in user with the given plans already made, newest last.
def _app_with_plans(monkeypatch, db_file, subjects=("DSA",), topics=("Recursion", "Graphs")):
    from auth.google_oauth import GoogleProfile
    from auth.service import user_context_for_profile
    from auth.streamlit_auth import session_store
    from db import plan_service
    from learning.planner import StudyGoal
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc.apps.googleusercontent.com")
    user = user_context_for_profile(
        GoogleProfile(google_id="google-1", email="ada@example.com", name="Ada")
    )
    made = [
        plan_service.create_plan(
            user.user_id,
            StudyGoal(subject=subject, topics=list(topics), hours_per_day=1.0,
                      target_date=(date.today() + timedelta(days=21)).isoformat()),
        )
        for subject in subjects
    ]
    app = AppTest.from_file(APP_FILE, default_timeout=120)
    app.session_state["auth_session_id"] = session_store().create(user).session_id
    app.run()
    return app, user, made
# Find a widget by key.
def _widget(collection, key):
    return next((widget for widget in collection if widget.key == key), None)
# Move to a section.
def _go(app, section):
    app.segmented_control[0].set_value(section).run()
    return app
# --- landing ------------------------------------------------------------
# Signing in opens the dashboard, not the tutor.
def test_the_app_opens_on_the_dashboard(monkeypatch, db_file):
    app, _user, _made = _app_with_plans(monkeypatch, db_file)
    assert not app.exception
    assert app.session_state["section"] == "Dashboard"
    assert any("Welcome back" in header.value for header in app.header)
# --- plan history -------------------------------------------------------
# Only the newest plan is active; the rest stay in the history.
def test_only_one_plan_is_active(monkeypatch, db_file):
    from db import plan_service
    _app, user, made = _app_with_plans(monkeypatch, db_file, subjects=("DSA", "SQL", "Python"))
    statuses = {record["id"]: record["status"] for record in plan_service.list_plans(user.user_id)}
    assert statuses[made[-1][0]] == "active"
    assert statuses[made[0][0]] == "archived"
    assert statuses[made[1][0]] == "archived"
    assert plan_service.active_plan(user.user_id)[0] == made[-1][0]
# Every plan ever made is listed, with the active one marked.
def test_all_plans_are_listed(monkeypatch, db_file):
    app, _user, made = _app_with_plans(monkeypatch, db_file, subjects=("DSA", "SQL", "Python"))
    _go(app, "Study Plan")
    assert not app.exception
    assert any("All your plans (3)" in str(element.label) for element in app.expander)
    for plan_id, _plan in made:
        assert _widget(app.button, f"delplan_{plan_id}") is not None
    # The newest is active, so it has no Open button; the older two do.
    assert _widget(app.button, f"openplan_{made[-1][0]}") is None
    assert _widget(app.button, f"openplan_{made[0][0]}") is not None
# Opening an older plan makes it the active one again.
def test_opening_an_older_plan_activates_it(monkeypatch, db_file):
    from db import plan_service
    app, user, made = _app_with_plans(monkeypatch, db_file, subjects=("DSA", "SQL"))
    _go(app, "Study Plan")
    _widget(app.button, f"openplan_{made[0][0]}").click().run()
    assert not app.exception
    active = plan_service.active_plan(user.user_id)
    assert active is not None
    assert active[0] == made[0][0]
    assert active[1].subject == "DSA"
# Deleting one plan leaves the others alone.
def test_deleting_one_plan(monkeypatch, db_file):
    from db import plan_service
    app, user, made = _app_with_plans(monkeypatch, db_file, subjects=("DSA", "SQL"))
    _go(app, "Study Plan")
    _widget(app.button, f"delplan_{made[0][0]}").click().run()
    assert not app.exception
    remaining = plan_service.list_plans(user.user_id)
    assert [record["id"] for record in remaining] == [made[1][0]]
# The reset button asks first, then removes every plan.
def test_reset_deletes_every_plan(monkeypatch, db_file):
    from db import plan_service
    app, user, made = _app_with_plans(monkeypatch, db_file, subjects=("DSA", "SQL"))
    _go(app, "Study Plan")
    _widget(app.button, "reset_plans").click().run()
    assert len(plan_service.list_plans(user.user_id)) == 2, "reset must confirm first"
    assert any("cannot be undone" in warning.value for warning in app.warning)
    _widget(app.checkbox, "confirm_reset_plans").set_value(True).run()
    _widget(app.button, "reset_plans").click().run()
    assert not app.exception
    assert plan_service.list_plans(user.user_id) == []
    assert plan_service.active_plan(user.user_id) is None
# Deleting the last plan returns the page to the goal form.
def test_deleting_the_last_plan_shows_the_form(monkeypatch, db_file):
    app, _user, made = _app_with_plans(monkeypatch, db_file)
    _go(app, "Study Plan")
    _widget(app.button, "delete_active_plan").click().run()
    assert not app.exception
    assert _widget(app.text_input, None) is not None or app.text_input
    assert any(widget.label == "Subject" for widget in app.text_input)
# --- the dashboard's view of the plan -----------------------------------
# The dashboard says which week it is and what to study now.
def test_dashboard_shows_the_current_plan_item(monkeypatch, db_file):
    app, _user, made = _app_with_plans(monkeypatch, db_file)
    _plan_id, plan = made[0]
    first = next(item for item in plan.items if item.status != "done")
    html = " ".join(element.value for element in app.get("html"))
    captions = " ".join(caption.value for caption in app.caption)
    assert any("Your plan: DSA" in sub.value for sub in app.subheader)
    assert "Week 1 of" in captions
    assert first.concept_name in html
    assert any(f"Learn {first.concept_name}" == button.label for button in app.button)
# The dashboard also offers a way into the full plan.
def test_dashboard_links_to_the_full_plan(monkeypatch, db_file):
    app, _user, _made = _app_with_plans(monkeypatch, db_file)
    opener = next(b for b in app.button if b.label == "Open the full plan")
    opener.click().run()
    assert not app.exception
    assert app.session_state["section"] == "Study Plan"
    assert any("Study plan" in header.value for header in app.header)
# Finishing everything is reported rather than showing an empty block.
def test_dashboard_when_the_plan_is_finished(monkeypatch, db_file):
    from db import plan_service
    app, user, made = _app_with_plans(monkeypatch, db_file)
    plan_id, plan = made[0]
    for item in plan.items:
        plan_service.complete_item(user.user_id, plan_id, item.concept_slug, item.week)
    app.run()
    assert not app.exception
    assert any("Everything in this plan is done" in success.value for success in app.success)
# With no plan at all the dashboard offers to make one.
def test_dashboard_without_a_plan(monkeypatch, db_file):
    app, _user, _made = _app_with_plans(monkeypatch, db_file, subjects=())
    assert not app.exception
    assert any("No plan yet" in caption.value for caption in app.caption)
    assert any(button.label == "Make a study plan" for button in app.button)
# --- isolation ----------------------------------------------------------
# Plans, and the ability to delete them, stay with their owner.
def test_plans_are_private(monkeypatch, db_file, users):
    from auth.errors import UnauthorizedError
    from db import plan_service
    _app, owner, made = _app_with_plans(monkeypatch, db_file)
    other = users.upsert_from_google("google-2", "bob@example.com", "Bob")
    plan_id = made[0][0]
    assert plan_service.load_plan(other.id, plan_id) is None
    assert plan_service.list_plans(other.id) == []
    assert plan_service.plan_focus(other.id) == {}
    assert plan_service.delete_plan(other.id, plan_id) is False
    assert plan_service.delete_all_plans(other.id) == 0
    with pytest.raises(UnauthorizedError):
        plan_service.activate_plan(other.id, plan_id)
    assert plan_service.load_plan(owner.user_id, plan_id) is not None
# --- the focus calculation ---------------------------------------------
# The current week follows the calendar, and falling behind is reported.
def test_plan_focus_tracks_the_weeks(monkeypatch, db_file):
    from db import plan_service
    _app, user, made = _app_with_plans(monkeypatch, db_file)
    today = date.today()
    first = plan_service.plan_focus(user.user_id, today)
    assert first["week"] == 1
    assert first["behind"] is False
    later = plan_service.plan_focus(user.user_id, today + timedelta(days=15))
    assert later["week"] == 3
    assert later["behind"] is True, "week 1 work still pending in week 3 means behind"
    assert later["current"] is not None

# Study material attached from inside Learn: picking a document, being quizzed on it, isolation.
from pathlib import Path
import pytest
AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
APP_FILE = str(Path(__file__).resolve().parents[1] / "app.py")
NOTES = b"""# Dynamic Programming

Dynamic programming solves problems with overlapping subproblems by storing results.
Memoization caches results from the top down, while tabulation fills a table bottom up.
"""
# A signed-in user in the Learn section, with the given documents already uploaded.
def _learn_app(monkeypatch, db_file, filenames=("dp.md",), google_id="google-1"):
    from auth.google_oauth import GoogleProfile
    from auth.service import user_context_for_profile
    from auth.streamlit_auth import session_store
    from rag import store
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc.apps.googleusercontent.com")
    user = user_context_for_profile(
        GoogleProfile(google_id=google_id, email=f"{google_id}@example.com", name="Ada")
    )
    documents = [
        store.ingest(user.user_id, name, NOTES.replace(b"Dynamic", name.encode() + b" Dynamic"))
        for name in filenames
    ]
    app = AppTest.from_file(APP_FILE, default_timeout=120)
    app.session_state["auth_session_id"] = session_store().create(user).session_id
    app.run()
    # The app opens on the dashboard, and study material lives in Learn.
    app.segmented_control[0].set_value("Learn").run()
    return app, user, documents
# Find a widget by key.
def _widget(collection, key):
    return next((widget for widget in collection if widget.key == key), None)
# Two usable questions, as the document quiz builder would return them.
def _fake_questions():
    return [
        {
            "question": "What does memoization do?",
            "options": ["Caches results", "Sorts data", "Frees memory", "Opens files"],
            "correct_answer": "Caches results",
            "explanation": "It stores the results of subproblems.",
        },
        {
            "question": "Which fills a table bottom up?",
            "options": ["Tabulation", "Memoization", "Recursion", "Hashing"],
            "correct_answer": "Tabulation",
            "explanation": "Tabulation works bottom up.",
        },
    ]
# There is no separate documents page any more.
def test_documents_section_is_gone(monkeypatch, db_file):
    app, _user, _documents = _learn_app(monkeypatch, db_file)
    assert not app.exception
    options = list(app.segmented_control[0].options)
    assert "My Documents" not in options
    assert options == [
        "Dashboard", "Learn", "Knowledge", "Coding Practice",
        "Today's Review", "Study Plan", "Analytics",
    ]
# The attach control lives in Learn and lists what has been uploaded.
def test_attach_control_is_in_learn(monkeypatch, db_file):
    app, _user, _documents = _learn_app(monkeypatch, db_file)
    picker = _widget(app.selectbox, "attach_pick")
    assert picker is not None
    assert "dp.md" in list(picker.options)
    # The picker only exists inside the attach popover, so finding it proves the control is there.
    assert app.get("popover")
# Picking a document attaches it to the session and says so.
def test_picking_a_document_attaches_it(monkeypatch, db_file):
    app, _user, documents = _learn_app(monkeypatch, db_file, ("dp.md", "trees.md"))
    _widget(app.selectbox, "attach_pick").set_value("trees.md").run()
    assert not app.exception
    attached = next(d for d in documents if d.filename == "trees.md")
    assert app.session_state["attached_document_id"] == attached.id
    assert any("Attached: **trees.md**" in caption.value for caption in app.caption)
# Asking to be quizzed on the document runs the quiz in the Learn section.
def test_quiz_from_document_runs_in_learn(monkeypatch, db_file):
    import ui.documents_ui as documents_ui
    app, _user, documents = _learn_app(monkeypatch, db_file)
    monkeypatch.setattr(
        documents_ui, "quiz_from_document", lambda *a, **k: (_fake_questions(), [])
    )
    monkeypatch.setattr(documents_ui, "_extract_concepts", lambda user, document: None)
    _widget(app.button, f"docquiz_{documents[0].id}").click().run()
    assert not app.exception
    assert app.session_state["section"] == "Learn"
    assert app.session_state["doc_quiz"]["document_id"] == documents[0].id
    assert len(app.session_state["doc_quiz"]["questions"]) == 2
    assert any("Quiz — dp.md" in header.value for header in app.header)
    assert len(app.radio) == 2
# Answering that quiz grades it and moves the document's concepts.
def test_document_quiz_updates_mastery(monkeypatch, db_file):
    import ui.documents_ui as documents_ui
    from db import learning_service
    from rag import store
    app, user, documents = _learn_app(monkeypatch, db_file)
    concepts = learning_service.register_names(["Memoization"], "DSA")
    store.set_document_concepts(user.user_id, documents[0].id, [c.slug for c in concepts])
    monkeypatch.setattr(
        documents_ui, "quiz_from_document", lambda *a, **k: (_fake_questions(), [])
    )
    monkeypatch.setattr(documents_ui, "_extract_concepts", lambda user, document: None)
    _widget(app.button, f"docquiz_{documents[0].id}").click().run()
    for index, answer in enumerate(["Caches results", "Tabulation"]):
        _widget(app.radio, f"docans_{index}").set_value(answer).run()
    submit = next(b for b in app.button if b.label == "Submit Quiz")
    submit.click().run()
    assert not app.exception
    state = learning_service.mastery_for_concept(user.user_id, concepts[0].slug)
    assert state is not None
    assert state.attempts == 1
    assert state.correct_attempts == 1
    assert any("Mastery updated" in sub.value for sub in app.subheader)
# A document belonging to someone else never appears in the picker.
def test_attach_only_lists_your_own_documents(monkeypatch, db_file):
    _owner_app, _owner, owned = _learn_app(monkeypatch, db_file, ("private.md",))
    app, _user, mine = _learn_app(monkeypatch, db_file, ("mine.md",), google_id="google-2")
    picker = _widget(app.selectbox, "attach_pick")
    assert list(picker.options) == ["mine.md"]
    assert _widget(app.button, f"docquiz_{owned[0].id}") is None
# With nothing uploaded the panel explains what to do instead of breaking.
def test_empty_library_is_handled(monkeypatch, db_file):
    app, _user, _documents = _learn_app(monkeypatch, db_file, ())
    assert not app.exception
    assert _widget(app.selectbox, "attach_pick") is None
    assert any("Nothing uploaded yet" in info.value for info in app.info)

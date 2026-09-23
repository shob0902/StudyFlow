# User creation, returning logins and the uniqueness rules on google_id and email.
import sqlite3
import pytest
from auth.errors import DatabaseError
# A first sign-in creates the user record with the Google identity.
def test_creates_user_on_first_login(users):
    user = users.upsert_from_google("google-1", "Ada@Example.com", "Ada Lovelace", "https://pic")
    assert user.id
    assert user.google_id == "google-1"
    assert user.email == "ada@example.com"
    assert user.name == "Ada Lovelace"
    assert user.profile_picture == "https://pic"
    assert user.created_at == user.last_login_at
    assert users.count() == 1
# Signing in again reuses the same record instead of creating a second one.
def test_existing_user_login_reuses_record(users):
    first = users.upsert_from_google("google-1", "ada@example.com", "Ada Lovelace")
    second = users.upsert_from_google("google-1", "ada@example.com", "Ada Lovelace")
    assert second.id == first.id
    assert users.count() == 1
# A returning user's changed name, picture and email are refreshed on the existing record.
def test_returning_user_profile_is_refreshed(users):
    first = users.upsert_from_google("google-1", "ada@example.com", "Ada L.")
    updated = users.upsert_from_google("google-1", "ada.new@example.com", "Ada Lovelace", "https://new")
    assert updated.id == first.id
    assert updated.email == "ada.new@example.com"
    assert updated.name == "Ada Lovelace"
    assert updated.profile_picture == "https://new"
    assert users.count() == 1
# google_id is unique at the database level, not just in application code.
def test_duplicate_google_id_is_rejected_by_the_schema(connection, users):
    users.upsert_from_google("google-1", "ada@example.com", "Ada")
    with pytest.raises(sqlite3.IntegrityError):
        with connection:
            connection.execute(
                "INSERT INTO users (id, google_id, email, name, profile_picture, created_at, last_login_at)"
                " VALUES ('x', 'google-1', 'other@example.com', 'Other', '', 'now', 'now')"
            )
    assert users.count() == 1
# Email is unique too, so a second Google account cannot claim an address already in use.
def test_same_email_under_a_different_google_id_is_refused(users):
    users.upsert_from_google("google-1", "ada@example.com", "Ada")
    with pytest.raises(DatabaseError):
        users.upsert_from_google("google-2", "ada@example.com", "Impostor")
    assert users.count() == 1
# Google's stable id, not the email, decides which record you get.
def test_google_id_is_the_identity_key(users):
    first = users.upsert_from_google("google-1", "shared@example.com", "Ada")
    users.upsert_from_google("google-1", "moved@example.com", "Ada")
    assert users.get_by_google_id("google-1").id == first.id
    assert users.get_by_email("moved@example.com").id == first.id
    assert users.get_by_email("shared@example.com") is None
# A missing Google id or email is refused rather than stored.
def test_incomplete_google_profile_is_refused(users):
    with pytest.raises(DatabaseError):
        users.upsert_from_google("", "ada@example.com", "Ada")
    with pytest.raises(DatabaseError):
        users.upsert_from_google("google-1", "", "Ada")
# Looking up an unknown user returns None rather than raising.
def test_unknown_lookups_return_none(users):
    assert users.get_by_id("nope") is None
    assert users.get_by_google_id("nope") is None
    assert users.get_by_email("nobody@example.com") is None

"""Tests for app.py's database helpers, exercised against the test database."""

import pytest
from werkzeug.security import check_password_hash

import app


def _copies_available(book_id):
    return app.get_books_by_ids([book_id])[book_id]["copies_available"]


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------
def test_create_user_stores_hashed_password(clean_db):
    uid = app.create_user("alice", "s3cret", role="admin", email="alice@example.com")
    assert uid is not None

    row = app.get_user_row(username="alice")
    id_, username, password_hash, role = row
    assert (id_, username, role) == (uid, "alice", "admin")
    assert password_hash != "s3cret"
    assert check_password_hash(password_hash, "s3cret")


def test_create_user_rejects_duplicate_username(clean_db):
    app.create_user("bob", "pw")
    with pytest.raises(ValueError, match="username exists"):
        app.create_user("bob", "other-pw")


def test_get_user_row_lookups(clean_db):
    uid = app.create_user("carol", "pw")
    assert app.get_user_row(user_id=uid)[1] == "carol"
    assert app.get_user_row(username="nobody") is None
    assert app.get_user_row() is None


def test_user_model_wraps_rows(clean_db):
    uid = app.create_user("dave", "pw", role="doctor")

    by_name = app.User.get_by_username("dave")
    assert (by_name.id, by_name.username, by_name.role) == (uid, "dave", "doctor")

    by_id = app.User.get_by_id(uid)
    assert by_id.username == "dave"

    assert app.User.get_by_username("missing") is None
    assert app.User.get_by_id(999999) is None


# ---------------------------------------------------------------------------
# books
# ---------------------------------------------------------------------------
def test_create_book_seeds_both_copy_counters(clean_db):
    bid = app.create_book("Moby Dick", "Herman Melville", "isbn-1", copies=3)
    book = app.get_books_by_ids([bid])[bid]
    assert book["title"] == "Moby Dick"
    assert book["author"] == "Herman Melville"
    assert book["copies_total"] == 3
    assert book["copies_available"] == 3


def test_create_book_defaults_to_one_copy(clean_db):
    bid = app.create_book("Solo")
    book = app.get_books_by_ids([bid])[bid]
    assert (book["copies_total"], book["copies_available"]) == (1, 1)
    assert book["author"] == ""


def test_get_all_books_is_sorted_by_title(clean_db):
    app.create_book("Zebra", "Z")
    app.create_book("Apple", "A")
    app.create_book("Mango", "M")
    assert [b["title"] for b in app.get_all_books()] == ["Apple", "Mango", "Zebra"]


def test_get_books_by_ids_empty_input_skips_query(clean_db):
    assert app.get_books_by_ids([]) == {}


def test_get_books_by_ids_ignores_unknown_ids(clean_db):
    bid = app.create_book("Known", "A")
    result = app.get_books_by_ids([bid, 999999])
    assert list(result) == [bid]


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------
@pytest.fixture()
def search_corpus(clean_db):
    return {
        "kokoro": app.create_book("こころ", "夏目 漱石"),
        "botchan": app.create_book("坊っちゃん", "夏目 漱石"),
        "gate": app.create_book("The Gate", "Natsume Soseki"),
        "rashomon": app.create_book("Rashomon", "Ryunosuke Akutagawa"),
    }


def test_search_without_tokens_returns_all_books(search_corpus):
    assert len(app.get_books_by_search_tokens([], [])) == 4


def test_search_ignores_blank_tokens(search_corpus):
    assert len(app.get_books_by_search_tokens(["", None], [""])) == 4


def test_search_by_title_token(search_corpus):
    hits = app.get_books_by_search_tokens(["Gate"], [])
    assert [h["title"] for h in hits] == ["The Gate"]


def test_search_title_is_case_insensitive(search_corpus):
    assert len(app.get_books_by_search_tokens(["rashOMon"], [])) == 1


def test_search_title_tokens_are_anded(search_corpus):
    assert app.get_books_by_search_tokens(["The", "Gate"], []) != []
    # "Gate" and "Rashomon" never co-occur in one title.
    assert app.get_books_by_search_tokens(["Gate", "Rashomon"], []) == []


def test_search_by_author_token(search_corpus):
    hits = app.get_books_by_search_tokens([], ["漱石"])
    assert sorted(h["title"] for h in hits) == sorted(["こころ", "坊っちゃん"])


def test_search_ors_title_group_with_author_group(search_corpus):
    # Title group matches Rashomon; author group matches the two 漱石 books.
    hits = app.get_books_by_search_tokens(["Rashomon"], ["漱石"])
    assert sorted(h["title"] for h in hits) == sorted(["Rashomon", "こころ", "坊っちゃん"])


def test_search_no_match_returns_empty(search_corpus):
    assert app.get_books_by_search_tokens(["nonexistent-title"], []) == []


def test_search_results_are_sorted_by_title(search_corpus):
    titles = [b["title"] for b in app.get_books_by_search_tokens([], [])]
    assert titles == sorted(titles)


# ---------------------------------------------------------------------------
# renting / inventory
# ---------------------------------------------------------------------------
def test_rent_decrements_available_copies(clean_db):
    uid = app.create_user("reader", "pw")
    bid = app.create_book("Dune", "Frank Herbert", copies=2)

    rid = app.create_rent_with_inventory(uid, bid)
    assert rid is not None
    assert _copies_available(bid) == 1
    assert app.get_books_by_ids([bid])[bid]["copies_total"] == 2


def test_rent_refuses_when_no_copies_left(clean_db):
    uid = app.create_user("reader", "pw")
    bid = app.create_book("Only One", "A", copies=1)

    assert app.create_rent_with_inventory(uid, bid) is not None
    assert _copies_available(bid) == 0
    # Second rent must fail rather than drive the counter negative.
    assert app.create_rent_with_inventory(uid, bid) is None
    assert _copies_available(bid) == 0


def test_rent_returns_none_for_unknown_book(clean_db):
    uid = app.create_user("reader", "pw")
    assert app.create_rent_with_inventory(uid, 999999) is None


def test_rent_accepts_explicit_rent_date(clean_db):
    uid = app.create_user("reader", "pw")
    bid = app.create_book("Dated", "A")

    app.create_rent_with_inventory(uid, bid, rent_date="2025-01-15")
    rows = app.get_rented_books_for_user(uid)
    assert rows[0]["rent_date"] == "2025-01-15"


def test_create_rent_without_inventory_does_not_touch_counters(clean_db):
    uid = app.create_user("reader", "pw")
    bid = app.create_book("Raw", "A", copies=2)

    assert app.create_rent(uid, bid) is not None
    assert _copies_available(bid) == 2


def test_has_active_rent_tracks_the_open_loan(clean_db):
    uid = app.create_user("reader", "pw")
    bid = app.create_book("Tracked", "A")

    assert app.has_active_rent(uid, bid) is False
    rid = app.create_rent_with_inventory(uid, bid)
    assert app.has_active_rent(uid, bid) is True

    app.mark_rent_returned_with_inventory(rid)
    assert app.has_active_rent(uid, bid) is False


def test_return_restores_inventory_once(clean_db):
    uid = app.create_user("reader", "pw")
    bid = app.create_book("Returnable", "A", copies=1)
    rid = app.create_rent_with_inventory(uid, bid)

    assert app.mark_rent_returned_with_inventory(rid) is True
    assert _copies_available(bid) == 1

    # Returning again must be a no-op, not a second increment.
    assert app.mark_rent_returned_with_inventory(rid) is False
    assert _copies_available(bid) == 1


def test_return_of_unknown_rent_id_is_false(clean_db):
    assert app.mark_rent_returned_with_inventory(999999) is False


def test_cancel_deletes_rent_and_restores_inventory(clean_db):
    uid = app.create_user("reader", "pw")
    bid = app.create_book("Cancellable", "A", copies=1)
    rid = app.create_rent_with_inventory(uid, bid)

    assert app.delete_rent_with_inventory(rid) is True
    assert _copies_available(bid) == 1
    assert app.get_rented_books_for_user(uid) == []


def test_cancel_of_returned_rent_deletes_without_double_increment(clean_db):
    uid = app.create_user("reader", "pw")
    bid = app.create_book("Already Back", "A", copies=1)
    rid = app.create_rent_with_inventory(uid, bid)
    app.mark_rent_returned_with_inventory(rid)

    assert app.delete_rent_with_inventory(rid) is True
    assert _copies_available(bid) == 1


def test_cancel_of_unknown_rent_id_is_false(clean_db):
    assert app.delete_rent_with_inventory(999999) is False


# ---------------------------------------------------------------------------
# rented-books listing (feeds the DataTable)
# ---------------------------------------------------------------------------
def test_rented_books_rows_shape_for_open_loan(clean_db):
    uid = app.create_user("reader", "pw")
    bid = app.create_book("Open Loan", "Some Author")
    rid = app.create_rent_with_inventory(uid, bid, rent_date="2025-03-01")

    (row,) = app.get_rented_books_for_user(uid)
    assert row["rent_id"] == rid
    assert row["book_id"] == bid
    assert row["title"] == "Open Loan"
    assert row["author"] == "Some Author"
    assert row["rent_date"] == "2025-03-01"
    assert row["return_date"] == ""
    assert row["return_action"] == "返却"
    assert row["cancel_action"] == "キャンセル"


def test_rented_books_hides_actions_once_returned(clean_db):
    uid = app.create_user("reader", "pw")
    bid = app.create_book("Closed Loan", "A")
    rid = app.create_rent_with_inventory(uid, bid)
    app.mark_rent_returned_with_inventory(rid)

    (row,) = app.get_rented_books_for_user(uid)
    assert row["return_date"] != ""
    assert row["return_action"] == ""
    assert row["cancel_action"] == ""


def test_rented_books_are_scoped_to_one_user(clean_db):
    u1 = app.create_user("u1", "pw")
    u2 = app.create_user("u2", "pw")
    b1 = app.create_book("Book One", "A", copies=5)
    app.create_rent_with_inventory(u1, b1)

    assert len(app.get_rented_books_for_user(u1)) == 1
    assert app.get_rented_books_for_user(u2) == []


def test_rented_books_newest_first(clean_db):
    uid = app.create_user("reader", "pw")
    old = app.create_book("Old", "A")
    new = app.create_book("New", "A")
    app.create_rent_with_inventory(uid, old, rent_date="2025-01-01")
    app.create_rent_with_inventory(uid, new, rent_date="2025-06-01")

    assert [r["title"] for r in app.get_rented_books_for_user(uid)] == ["New", "Old"]


# ---------------------------------------------------------------------------
# schema bootstrap
# ---------------------------------------------------------------------------
def test_ensure_tables_is_idempotent_and_reconciles_inventory(clean_db):
    uid = app.create_user("reader", "pw")
    bid = app.create_book("Drifted", "A", copies=3)
    app.create_rent(uid, bid)  # rent row without touching the counter
    assert _copies_available(bid) == 3

    app.ensure_tables()

    # ensure_tables recomputes availability from open rent rows.
    assert _copies_available(bid) == 2

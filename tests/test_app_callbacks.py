"""
Tests for app.py's Dash callbacks.

The callbacks are exercised through the real /_dash-update-component endpoint so
that the request context, Flask-Login session and callback_context all behave the
way they do in the running app.
"""

import json

import pytest

import app


# ---------------------------------------------------------------------------
# dispatch helpers
# ---------------------------------------------------------------------------
def _outputs_spec(output_key):
    """Turn a callback_map key into the `outputs` payload Dash expects."""
    if output_key.startswith(".."):
        parts = output_key.strip(".").split("...")
        return [
            {"id": p.rsplit(".", 1)[0], "property": p.rsplit(".", 1)[1]} for p in parts
        ]
    cid, prop = output_key.rsplit(".", 1)
    return {"id": cid, "property": prop}


def dispatch(client, output_key, inputs, state=None, changed=None):
    """
    Invoke one callback and return {component_id: {prop: value}}.

    `inputs`/`state` are (id, property, value) triples in callback-signature order.
    Returns None when the callback raised PreventUpdate (HTTP 204).
    """
    body = {
        "output": output_key,
        "outputs": _outputs_spec(output_key),
        "inputs": [{"id": i, "property": p, "value": v} for i, p, v in inputs],
        "state": [{"id": i, "property": p, "value": v} for i, p, v in (state or [])],
        "changedPropIds": changed if changed is not None else [f"{i}.{p}" for i, p, _ in inputs],
    }
    resp = client.post("/_dash-update-component", json=body)
    if resp.status_code == 204:
        return None
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()["response"]


SEARCH_STORE = "search-store.data"
CLEAR_FORM = "..search-title.value...search-author.value...books-dropdown.value.."
BOOKS_DROPDOWN = "..books-dropdown.options...search-results.children...search-last-searched.data.."
SELECTION_SUMMARY = "..books-selection-summary.children...confirm-modal-body.children.."
RENT_ACTIONS = "..rent-book-result.children...rents-action-result.children...rents-refresh.data...confirm-modal.style.."
RENTS_TABLE = "rents-table.data"
DEBUG_SELECTION = "..debug-dropdown-value.children...debug-books-selected-store.children.."


def update_search_store(client, title, author, clear_clicks=0, changed=None):
    return dispatch(
        client,
        SEARCH_STORE,
        [
            ("search-title", "value", title),
            ("search-author", "value", author),
            ("books-clear-btn", "n_clicks", clear_clicks),
        ],
        state=[("search-store", "data", {"title": "", "author": "", "last_input_ts": 0})],
        changed=changed,
    )


def load_dropdown(client, title="", author="", selected=None, last_searched=0):
    return dispatch(
        client,
        BOOKS_DROPDOWN,
        [
            ("load-once", "n_intervals", 1),
            ("rents-refresh", "data", 0),
            ("books-search-btn", "n_clicks", 0),
            ("search-interval", "n_intervals", 0),
            ("search-store", "data", {"title": title, "author": author, "last_input_ts": 1}),
        ],
        state=[
            ("search-last-searched", "data", last_searched),
            ("books-dropdown", "value", selected),
        ],
        changed=["search-store.data"],
    )


def selection_summary(client, selected, stored=None):
    return dispatch(
        client,
        SELECTION_SUMMARY,
        [("books-dropdown", "value", selected)],
        state=[("books-selected-store", "data", stored)],
    )


def rent_action(client, trigger, selected=None, active_cell=None, table_data=None):
    """`trigger` is e.g. 'rent-book-btn.n_clicks' or 'rents-table.active_cell'."""
    return dispatch(
        client,
        RENT_ACTIONS,
        [
            ("rent-book-btn", "n_clicks", 1),
            ("confirm-rent-btn", "n_clicks", 1),
            ("cancel-rent-btn", "n_clicks", 1),
            ("rents-table", "active_cell", active_cell),
        ],
        state=[
            ("books-dropdown", "value", selected),
            ("rents-table", "data", table_data or []),
        ],
        changed=[trigger],
    )


def load_rents(client):
    return dispatch(
        client,
        RENTS_TABLE,
        [
            ("rents-refresh", "data", 0),
            ("refresh-rents", "n_clicks", 0),
            ("load-once", "n_intervals", 1),
        ],
        changed=["load-once.n_intervals"],
    )


@pytest.fixture()
def user(client):
    """A logged-in user; returns their id."""
    uid = app.create_user("reader", "pw")
    client.post("/do_login", data={"username": "reader", "password": "pw"})
    return uid


def _text(value):
    """Flatten a serialized Dash component tree to a searchable string."""
    return json.dumps(value, ensure_ascii=False)


# ---------------------------------------------------------------------------
# search-store
# ---------------------------------------------------------------------------
def test_search_store_normalizes_input(client):
    store = update_search_store(client, "　こころ　", "  夏目   漱石 ")["search-store"]["data"]
    assert store["title"] == "こころ"
    assert store["author"] == "夏目 漱石"
    assert store["last_input_ts"] > 0


def test_search_store_treats_none_as_empty(client):
    store = update_search_store(client, None, None)["search-store"]["data"]
    assert store["title"] == ""
    assert store["author"] == ""


def test_clear_button_resets_the_search_store(client):
    store = update_search_store(
        client, "something", "someone", clear_clicks=1, changed=["books-clear-btn.n_clicks"]
    )["search-store"]["data"]
    assert store["title"] == ""
    assert store["author"] == ""


def test_clear_button_empties_the_search_boxes(client):
    resp = dispatch(client, CLEAR_FORM, [("books-clear-btn", "n_clicks", 1)])
    assert resp["search-title"]["value"] == ""
    assert resp["search-author"]["value"] == ""


def test_clear_button_drops_the_dropdown_selection(client):
    resp = dispatch(client, CLEAR_FORM, [("books-clear-btn", "n_clicks", 1)])
    assert resp["books-dropdown"]["value"] == []


def test_clear_button_does_not_write_the_selected_store(client):
    # The clientside callback owns books-selected-store; a second writer would be
    # a duplicate-output error and would fight it for ownership.
    resp = dispatch(client, CLEAR_FORM, [("books-clear-btn", "n_clicks", 1)])
    assert "books-selected-store" not in resp


def test_cleared_form_shows_nothing_selected(client, corpus, user):
    # State the summary callback sees once the clear has propagated.
    resp = selection_summary(client, [], stored=[])
    assert "選択されていません" in _text(resp["books-selection-summary"]["children"])
    assert "選択されていません" in _text(resp["confirm-modal-body"]["children"])


def test_cleared_boxes_feed_an_empty_search_store(client):
    # The blanked inputs re-trigger update_search_store_combined; the store must
    # stay empty rather than resurrect the old query.
    store = update_search_store(
        client, "", "", changed=["search-title.value"]
    )["search-store"]["data"]
    assert store["title"] == ""
    assert store["author"] == ""


# ---------------------------------------------------------------------------
# books dropdown / search results
# ---------------------------------------------------------------------------
@pytest.fixture()
def corpus(clean_db):
    return {
        "kokoro": app.create_book("こころ", "夏目 漱石", copies=2),
        "gate": app.create_book("The Gate", "Natsume Soseki", copies=1),
        "rashomon": app.create_book("Rashomon", "Ryunosuke Akutagawa", copies=3),
    }


def test_dropdown_lists_all_books_when_query_is_empty(client, corpus):
    resp = load_dropdown(client)
    options = resp["books-dropdown"]["options"]
    assert len(options) == 3
    # no query means no highlighted result list
    assert resp["search-results"]["children"] == []


def test_dropdown_option_labels_show_author_and_availability(client, corpus):
    options = load_dropdown(client)["books-dropdown"]["options"]
    labels = {o["label"] for o in options}
    assert "Rashomon / Ryunosuke Akutagawa (3 available)" in labels


def test_dropdown_option_values_are_string_ids(client, corpus):
    options = load_dropdown(client)["books-dropdown"]["options"]
    assert {o["value"] for o in options} == {str(v) for v in corpus.values()}


def test_dropdown_filters_on_query(client, corpus):
    resp = load_dropdown(client, title="Gate")
    options = resp["books-dropdown"]["options"]
    assert [o["value"] for o in options] == [str(corpus["gate"])]


def test_search_results_highlight_the_matched_token(client, corpus):
    resp = load_dropdown(client, title="Gate")
    rendered = _text(resp["search-results"]["children"])
    assert "Mark" in rendered
    assert "Gate" in rendered


def test_search_results_are_empty_without_a_query(client, corpus):
    assert load_dropdown(client)["search-results"]["children"] == []


def test_dropdown_keeps_a_selected_book_that_the_query_filters_out(client, corpus):
    # Search for "Gate" while こころ is selected: こころ must survive as an option,
    # otherwise the dropdown would silently drop the user's selection.
    resp = load_dropdown(client, title="Gate", selected=[str(corpus["kokoro"])])
    values = [o["value"] for o in resp["books-dropdown"]["options"]]
    assert str(corpus["kokoro"]) in values
    assert str(corpus["gate"]) in values


def test_dropdown_ignores_unparsable_selected_values(client, corpus):
    resp = load_dropdown(client, title="Gate", selected=["not-an-id"])
    assert [o["value"] for o in resp["books-dropdown"]["options"]] == [str(corpus["gate"])]


def test_dropdown_accepts_a_scalar_selection(client, corpus):
    resp = load_dropdown(client, title="Gate", selected=str(corpus["kokoro"]))
    values = [o["value"] for o in resp["books-dropdown"]["options"]]
    assert str(corpus["kokoro"]) in values


# ---------------------------------------------------------------------------
# selection summary / confirm modal body
# ---------------------------------------------------------------------------
def test_selection_summary_is_blank_for_anonymous_visitors(client, corpus):
    resp = selection_summary(client, [str(corpus["gate"])])
    assert _text(resp["books-selection-summary"]["children"]) == _text({"props": {"children": ""}, "type": "Div", "namespace": "dash_html_components"})


def test_selection_summary_reports_nothing_selected(client, corpus, user):
    resp = selection_summary(client, [])
    assert "選択されていません" in _text(resp["books-selection-summary"]["children"])
    assert "選択されていません" in _text(resp["confirm-modal-body"]["children"])


def test_selection_summary_lists_titles_and_availability(client, corpus, user):
    resp = selection_summary(client, [str(corpus["gate"])])
    summary = _text(resp["books-selection-summary"]["children"])
    assert "The Gate" in summary
    assert "Natsume Soseki" in summary
    assert "利用可能" in summary


def test_selection_summary_flags_a_book_already_rented(client, corpus, user):
    app.create_rent_with_inventory(user, corpus["gate"])
    resp = selection_summary(client, [str(corpus["gate"])])
    assert "既にレンタル中" in _text(resp["books-selection-summary"]["children"])


def test_selection_summary_falls_back_to_the_store(client, corpus, user):
    resp = selection_summary(client, None, stored=[corpus["gate"]])
    assert "The Gate" in _text(resp["books-selection-summary"]["children"])


def test_selection_summary_covers_every_selected_book(client, corpus, user):
    resp = selection_summary(client, [str(corpus["gate"]), str(corpus["kokoro"])])
    summary = _text(resp["books-selection-summary"]["children"])
    assert "The Gate" in summary
    assert "こころ" in summary


# ---------------------------------------------------------------------------
# rent / confirm / table actions
# ---------------------------------------------------------------------------
def test_rent_button_requires_a_login(client, corpus):
    resp = rent_action(client, "rent-book-btn.n_clicks", selected=[str(corpus["gate"])])
    assert "ログインが必要です" in _text(resp["rent-book-result"]["children"])
    assert resp["confirm-modal"]["style"] == {"display": "none"}


def test_rent_button_without_a_selection_asks_for_one(client, corpus, user):
    resp = rent_action(client, "rent-book-btn.n_clicks", selected=[])
    assert "本を選んでください" in _text(resp["rent-book-result"]["children"])
    assert "confirm-modal" not in resp


def test_rent_button_rejects_a_selection_with_no_valid_ids(client, corpus, user):
    resp = rent_action(client, "rent-book-btn.n_clicks", selected=["abc"])
    assert "有効な本が選択されていません" in _text(resp["rent-book-result"]["children"])


def test_rent_button_opens_the_confirm_modal(client, corpus, user):
    resp = rent_action(client, "rent-book-btn.n_clicks", selected=[str(corpus["gate"])])
    assert resp["confirm-modal"]["style"]["display"] == "block"
    # opening the modal must not create a rent yet
    assert app.get_rented_books_for_user(user) == []


def test_confirm_creates_the_rent_and_closes_the_modal(client, corpus, user):
    resp = rent_action(client, "confirm-rent-btn.n_clicks", selected=[str(corpus["gate"])])
    assert "1 件レンタル登録しました" in _text(resp["rent-book-result"]["children"])
    assert resp["confirm-modal"]["style"] == {"display": "none"}
    assert resp["rents-refresh"]["data"] > 0

    rows = app.get_rented_books_for_user(user)
    assert [r["title"] for r in rows] == ["The Gate"]
    assert app.get_books_by_ids([corpus["gate"]])[corpus["gate"]]["copies_available"] == 0


def test_confirm_rents_several_books_at_once(client, corpus, user):
    rent_action(
        client,
        "confirm-rent-btn.n_clicks",
        selected=[str(corpus["gate"]), str(corpus["kokoro"])],
    )
    assert len(app.get_rented_books_for_user(user)) == 2


def test_confirm_reports_out_of_stock_books_as_skipped(client, corpus, user):
    other = app.create_user("someone-else", "pw")
    app.create_rent_with_inventory(other, corpus["gate"])  # last copy is gone

    resp = rent_action(client, "confirm-rent-btn.n_clicks", selected=[str(corpus["gate"])])
    message = _text(resp["rent-book-result"]["children"])
    assert "スキップ" in message
    assert "The Gate" in message
    assert "在庫なし" in message
    assert app.get_rented_books_for_user(user) == []


def test_confirm_mixes_successes_and_skips(client, corpus, user):
    other = app.create_user("someone-else", "pw")
    app.create_rent_with_inventory(other, corpus["gate"])

    resp = rent_action(
        client,
        "confirm-rent-btn.n_clicks",
        selected=[str(corpus["gate"]), str(corpus["kokoro"])],
    )
    message = _text(resp["rent-book-result"]["children"])
    assert "1 件レンタル登録しました" in message
    assert "スキップ" in message


def test_confirm_without_a_selection_closes_the_modal(client, corpus, user):
    resp = rent_action(client, "confirm-rent-btn.n_clicks", selected=[])
    assert "選択が無効です" in _text(resp["rent-book-result"]["children"])
    assert resp["confirm-modal"]["style"] == {"display": "none"}


def test_cancel_button_just_closes_the_modal(client, corpus, user):
    resp = rent_action(client, "cancel-rent-btn.n_clicks", selected=[str(corpus["gate"])])
    assert resp["confirm-modal"]["style"] == {"display": "none"}
    assert app.get_rented_books_for_user(user) == []


def test_table_click_returns_a_book(client, corpus, user):
    app.create_rent_with_inventory(user, corpus["gate"])
    rows = app.get_rented_books_for_user(user)

    resp = rent_action(
        client,
        "rents-table.active_cell",
        active_cell={"row": 0, "column_id": "return_action"},
        table_data=rows,
    )
    assert "返却しました" in _text(resp["rents-action-result"]["children"])
    assert app.has_active_rent(user, corpus["gate"]) is False
    assert app.get_books_by_ids([corpus["gate"]])[corpus["gate"]]["copies_available"] == 1


def test_table_click_on_an_already_returned_row_is_reported(client, corpus, user):
    rid = app.create_rent_with_inventory(user, corpus["gate"])
    app.mark_rent_returned_with_inventory(rid)
    rows = app.get_rented_books_for_user(user)

    resp = rent_action(
        client,
        "rents-table.active_cell",
        active_cell={"row": 0, "column_id": "return_action"},
        table_data=rows,
    )
    assert "既に返却済みです" in _text(resp["rents-action-result"]["children"])


def test_table_click_cancels_a_rent(client, corpus, user):
    app.create_rent_with_inventory(user, corpus["gate"])
    rows = app.get_rented_books_for_user(user)

    resp = rent_action(
        client,
        "rents-table.active_cell",
        active_cell={"row": 0, "column_id": "cancel_action"},
        table_data=rows,
    )
    assert "レンタルをキャンセルしました" in _text(resp["rents-action-result"]["children"])
    assert app.get_rented_books_for_user(user) == []
    assert app.get_books_by_ids([corpus["gate"]])[corpus["gate"]]["copies_available"] == 1


def test_table_click_on_a_plain_column_does_nothing(client, corpus, user):
    app.create_rent_with_inventory(user, corpus["gate"])
    rows = app.get_rented_books_for_user(user)

    resp = rent_action(
        client,
        "rents-table.active_cell",
        active_cell={"row": 0, "column_id": "title"},
        table_data=rows,
    )
    assert resp is None  # PreventUpdate
    assert app.has_active_rent(user, corpus["gate"]) is True


def test_table_click_without_an_active_cell_does_nothing(client, corpus, user):
    resp = rent_action(client, "rents-table.active_cell", active_cell=None, table_data=[])
    assert resp is None


@pytest.mark.parametrize(
    "active_cell",
    [{"row": None, "column_id": "return_action"}, {"row": 0, "column_id": None}, {}],
)
def test_table_click_with_an_incomplete_active_cell_does_nothing(
    client, corpus, user, active_cell
):
    app.create_rent_with_inventory(user, corpus["gate"])
    rows = app.get_rented_books_for_user(user)

    resp = rent_action(
        client, "rents-table.active_cell", active_cell=active_cell, table_data=rows
    )
    assert resp is None
    assert app.has_active_rent(user, corpus["gate"]) is True


def test_unrecognised_trigger_does_nothing(client, corpus, user):
    # Falls through to the final `else: raise PreventUpdate`.
    resp = rent_action(client, "search-interval.n_intervals", selected=[])
    assert resp is None


def test_a_real_error_still_reports_to_the_user(client, corpus, user, monkeypatch):
    # The PreventUpdate re-raise must not swallow genuine failures.
    def boom(*a, **kw):
        raise RuntimeError("db is down")

    monkeypatch.setattr(app, "create_rent_with_inventory", boom)
    resp = rent_action(client, "confirm-rent-btn.n_clicks", selected=[str(corpus["gate"])])
    assert "スキップ" in _text(resp["rent-book-result"]["children"])
    assert "サーバエラー" in _text(resp["rent-book-result"]["children"])


# ---------------------------------------------------------------------------
# rents table loader
# ---------------------------------------------------------------------------
def test_rents_table_is_empty_for_anonymous_visitors(client, corpus):
    assert load_rents(client)["rents-table"]["data"] == []


def test_rents_table_lists_the_users_rents(client, corpus, user):
    app.create_rent_with_inventory(user, corpus["gate"])
    rows = load_rents(client)["rents-table"]["data"]
    assert [r["title"] for r in rows] == ["The Gate"]
    assert rows[0]["return_action"] == "返却"


def test_rents_table_does_not_leak_other_users_rents(client, corpus, user):
    other = app.create_user("someone-else", "pw")
    app.create_rent_with_inventory(other, corpus["kokoro"])
    assert load_rents(client)["rents-table"]["data"] == []


# ---------------------------------------------------------------------------
# debug callback
# ---------------------------------------------------------------------------
def test_debug_callback_echoes_the_current_selection(client, corpus):
    resp = dispatch(
        client,
        DEBUG_SELECTION,
        [
            ("books-dropdown", "value", ["7"]),
            ("books-selected-store", "data", [7]),
        ],
    )
    assert "['7']" in _text(resp["debug-dropdown-value"]["children"])
    assert "[7]" in _text(resp["debug-books-selected-store"]["children"])

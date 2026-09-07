"""
Tests for app.py's clientside callback (dropdown.value -> books-selected-store).

The JavaScript is executed in Node exactly as Dash ships it to the browser: the
source is pulled from app._inline_scripts rather than re-typed here, so these
tests break if the shipped function changes.
"""

import json
import shutil
import subprocess
import textwrap

import pytest

import app

NODE = shutil.which("node") or shutil.which("nodejs")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

@pytest.fixture(scope="module")
def inline_script():
    """The clientside callback source Dash injects into the page."""
    scripts = app.app._inline_scripts
    assert len(scripts) == 1, "expected exactly one inline clientside script"
    return scripts[0]


def run_clientside(inline_script, dropdown_value, clear_n, triggered, cache=None, options=None):
    """
    Invoke the real clientside callback under Node.

    `triggered` is the list of prop_ids Dash would report as having fired.
    Returns (return_value, window.__books_selected_cache after the call).
    """
    harness = textwrap.dedent(
        """
        const window = globalThis;
        window.dash_clientside = {};
        %(script)s
        window.__books_selected_cache = %(cache)s;
        window.dash_clientside.callback_context = {
            triggered: %(triggered)s.map(function(p) { return {prop_id: p, value: null}; })
        };
        const funcs = window.dash_clientside["_dashprivate_clientside_funcs"];
        const keys = Object.keys(funcs);
        if (keys.length !== 1) { throw new Error("expected 1 clientside func, got " + keys.length); }
        const fn = funcs[keys[0]];  // key is a hash of the source, so never hardcode it
        const out = fn(%(value)s, %(clear_n)s, %(options)s);
        console.log(JSON.stringify({out: out, cache: window.__books_selected_cache}));
        """
    ) % {
        "script": inline_script,
        "cache": json.dumps(cache),
        "triggered": json.dumps(triggered),
        "value": json.dumps(dropdown_value),
        "clear_n": json.dumps(clear_n),
        "options": json.dumps(options or []),
    }

    proc = subprocess.run(
        [NODE, "--input-type=module", "-e", harness],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    return result["out"], result["cache"]


# ---------------------------------------------------------------------------
# the regression this fix is about
# ---------------------------------------------------------------------------
def test_selection_still_syncs_after_the_clear_button_was_used(inline_script):
    # n_clicks stays >= 1 forever once クリア has been pressed. A later selection
    # must still reach the store instead of being flattened to [].
    out, cache = run_clientside(
        inline_script,
        dropdown_value=["3", "7"],
        clear_n=1,
        triggered=["books-dropdown.value"],
    )
    assert out == [3, 7]
    assert cache == [3, 7]


def test_selection_syncs_after_many_clear_clicks(inline_script):
    out, _ = run_clientside(
        inline_script,
        dropdown_value=["42"],
        clear_n=17,
        triggered=["books-dropdown.value"],
    )
    assert out == [42]


# ---------------------------------------------------------------------------
# clearing
# ---------------------------------------------------------------------------
def test_clear_click_empties_the_store_and_cache(inline_script):
    out, cache = run_clientside(
        inline_script,
        dropdown_value=["3", "7"],
        clear_n=1,
        triggered=["books-clear-btn.n_clicks"],
        cache=[3, 7],
    )
    assert out == []
    assert cache == []


def test_cleared_dropdown_value_normalizes_to_empty(inline_script):
    # clear_search_form sets the dropdown to []; that must not fall back to cache.
    out, cache = run_clientside(
        inline_script,
        dropdown_value=[],
        clear_n=1,
        triggered=["books-dropdown.value"],
        cache=[3, 7],
    )
    assert out == []
    assert cache == []


# ---------------------------------------------------------------------------
# normalization
# ---------------------------------------------------------------------------
def test_string_ids_become_ints(inline_script):
    out, _ = run_clientside(inline_script, ["1", "2"], 0, ["books-dropdown.value"])
    assert out == [1, 2]


def test_duplicates_are_dropped_preserving_order(inline_script):
    out, _ = run_clientside(inline_script, ["5", "3", "5"], 0, ["books-dropdown.value"])
    assert out == [5, 3]


def test_nested_arrays_are_flattened_one_level(inline_script):
    out, _ = run_clientside(inline_script, [["1", "2"], "3"], 0, ["books-dropdown.value"])
    assert out == [1, 2, 3]


def test_scalar_value_is_accepted(inline_script):
    out, _ = run_clientside(inline_script, "9", 0, ["books-dropdown.value"])
    assert out == [9]


def test_unparsable_values_are_skipped(inline_script):
    out, _ = run_clientside(inline_script, ["4", "abc", None], 0, ["books-dropdown.value"])
    assert out == [4]


# ---------------------------------------------------------------------------
# transient states
# ---------------------------------------------------------------------------
def test_null_value_falls_back_to_the_cache(inline_script):
    # Happens transiently while options are being replaced mid-search.
    out, _ = run_clientside(
        inline_script, None, 0, ["books-dropdown.value"], cache=[3, 7]
    )
    assert out == [3, 7]


def test_null_value_with_no_cache_yields_empty(inline_script):
    out, _ = run_clientside(inline_script, None, 0, ["books-dropdown.value"])
    assert out == []


def test_initial_call_with_no_trigger_does_not_clear(inline_script):
    out, _ = run_clientside(inline_script, ["8"], None, triggered=[])
    assert out == [8]

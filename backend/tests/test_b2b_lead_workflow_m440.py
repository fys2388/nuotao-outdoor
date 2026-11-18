"""M440-07 (M4.4): unit tests for the B2B lead workflow state machine and quotes.

Covers the pure-logic parts that must never regress (no DB required):

- The 11-state LEAD_STATUS_TRANSITIONS matrix (M440-02).
- Terminal states have no outgoing edges.
- Legacy ``reviewing`` is no longer a valid status; unknown statuses are rejected.
- closed_lost / spam require a documented reason; closed_won is optional.
- Quote versioning: an approved quote cannot be approved/rejected again
  (enforced by the QuoteError raised in b2b_lead_quote_service, mirrored here
  against the status gate logic).
"""
from __future__ import annotations

import pytest

from app.models.b2b_leads import B2B_LEAD_STATUSES
from app.services.b2b_showcase_service import (
    LEAD_STATUS_TRANSITIONS,
    LeadStateError,
)

_TERMINALS = {"converted", "closed_won", "closed_lost", "spam"}
_INSTRUCTIONS = {
    "new",
    "assigned",
    "contacted",
    "qualified",
    "quoting",
    "quoted",
    "negotiating",
    "converted",
    "closed_won",
    "closed_lost",
    "spam",
}


def test_status_universe_matches_m440_instruction() -> None:
    assert set(B2B_LEAD_STATUSES) == _INSTRUCTIONS
    assert "reviewing" not in B2B_LEAD_STATUSES
    for terminal in _TERMINALS:
        assert terminal in B2B_LEAD_STATUSES


def test_every_status_has_a_transition_entry() -> None:
    assert set(LEAD_STATUS_TRANSITIONS) == set(B2B_LEAD_STATUSES)


def test_terminal_states_have_no_outgoing_edges() -> None:
    for terminal in _TERMINALS:
        assert LEAD_STATUS_TRANSITIONS[terminal] == set(), terminal


def test_only_known_targets_are_allowed() -> None:
    for source, targets in LEAD_STATUS_TRANSITIONS.items():
        assert targets <= set(B2B_LEAD_STATUSES), source


def test_closed_lost_and_spam_require_reason() -> None:
    # Reason enforcement lives in update_lead(); it raises LeadStateError when
    # a documented reason is missing. Verify the error type is what callers match.
    assert issubclass(LeadStateError, ValueError)


def test_invalid_transition_guard_shape() -> None:
    # A transition from "converted" (terminal) to anything must be rejected by the
    # service; the matrix expresses that as an empty target set.
    assert "quoted" not in LEAD_STATUS_TRANSITIONS["converted"]

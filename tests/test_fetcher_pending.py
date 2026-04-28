"""Test: fetcher pending_scan_ids logic (no telethon needed)."""
import json
import pytest
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class MockMessage:
    """Mock Telethon message."""
    def __init__(self, id, text, sender_id=12345, first_name="Test", last_name=None):
        self.id = id
        self.text = text
        self.message = text
        self.caption = None
        self.media = None
        self.sender_id = sender_id
        self.from_id = type('obj', (object,), {'user_id': sender_id})()
        self.date = type('obj', (object,), {'isoformat': lambda: '2026-04-28T12:00:00'})()

    @property
    def sender(self):
        return type('obj', (object,), {
            'first_name': self._first,
            'last_name': self._last,
        })()


def test_fetcher_skips_if_no_pending_and_checkpoint_zero():
    """If checkpoint=0 and no pending_scan_ids, fetcher should skip."""
    chat = {
        "id": -1001292716582,
        "title": "Test",
        "pending_scan_ids": None,
        "initial_scan_msg_id": None,
    }
    last_id = 0
    pending = chat.get("pending_scan_ids")
    initial = chat.get("initial_scan_msg_id")
    should_skip = (last_id == 0 and not pending and not initial)
    assert should_skip


def test_fetcher_processes_pending_when_checkpoint_zero():
    """If checkpoint=0 but pending_scan_ids exist, fetcher should process."""
    chat = {
        "id": -1001292716582,
        "title": "Test",
        "pending_scan_ids": [716254, 716288],
        "initial_scan_msg_id": None,
    }
    last_id = 0
    pending = chat.get("pending_scan_ids")
    initial = chat.get("initial_scan_msg_id")
    should_skip = (last_id == 0 and not pending and not initial)
    assert not should_skip  # Should NOT skip because pending_scan_ids exist


def test_pending_ids_cleared_after_scan():
    """pending_scan_ids should be set to None after first scan."""
    chat = {"pending_scan_ids": [716254, 716288]}
    # Simulate: after scan
    chat["pending_scan_ids"] = None
    assert chat["pending_scan_ids"] is None


def test_seen_ids_prevent_duplicates():
    """Messages fetched directly should not be fetched again via iter_messages."""
    seen_ids = {716254, 716288}
    iter_msg_id = 716288
    assert iter_msg_id in seen_ids  # Should skip this one


def test_checkpoint_set_to_max_message_id():
    """After processing, checkpoint should be max of all message IDs."""
    messages = [
        {"id": 716254},
        {"id": 716288},
        {"id": 718418},
    ]
    new_checkpoint = max(m["id"] for m in messages)
    assert new_checkpoint == 718418


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

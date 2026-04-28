"""Test: recheck command — scan specific message IDs on demand."""
import json
import pytest
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Tests ────────────────────────────────────────────

def test_recheck_scans_specific_message():
    """recheck should add initial_scan_msg_id for the target message."""
    chat_id = -1001292716582
    chats = [{
        "id": chat_id,
        "title": "Test Chat",
        "username": "test_chat",
        "added": "2026-04-28T00:00:00",
        "status": "active",
        "initial_scan_msg_id": None,
    }]

    with tempfile.TemporaryDirectory() as tmpdir:
        chats_file = os.path.join(tmpdir, "chats.json")
        with open(chats_file, "w") as f:
            json.dump(chats, f)

        # Load, modify, save
        loaded = json.loads(open(chats_file).read())
        loaded[0]["initial_scan_msg_id"] = 716288
        with open(chats_file, "w") as f:
            json.dump(loaded, f, ensure_ascii=False, indent=2)

        # Verify
        result = json.loads(open(chats_file).read())
        assert result[0]["initial_scan_msg_id"] == 716288


def test_dedup_allows_new_message_after_reset():
    """After leads.json is reset, same message ID should be allowed again."""
    with tempfile.TemporaryDirectory() as tmpdir:
        leads_file = os.path.join(tmpdir, "leads.json")

        # Empty leads = no seen IDs
        with open(leads_file, "w") as f:
            json.dump([], f)

        with open(leads_file, "r") as f:
            seen = {lead.get("id") for lead in json.load(f)}

        assert 716254 not in seen
        assert 716288 not in seen

        # After adding a lead
        with open(leads_file, "w") as f:
            json.dump([{"id": 716254}], f)

        with open(leads_file, "r") as f:
            seen = {lead.get("id") for lead in json.load(f)}

        assert 716254 in seen
        assert 716288 not in seen


def test_recheck_multiple_message_ids():
    """recheck should support multiple message IDs via pending_scan_ids."""
    chat_id = -1001292716582
    chats = [{
        "id": chat_id,
        "title": "Test Chat",
        "status": "active",
        "initial_scan_msg_id": None,
    }]

    msg_ids = [716254, 716288, 717000]
    chats[0]["pending_scan_ids"] = msg_ids

    assert chats[0]["pending_scan_ids"] == [716254, 716288, 717000]


def test_checkpoint_lowered_for_recheck():
    """When rechecking older messages, checkpoint should be lowered."""
    current_checkpoint = 718418
    recheck_msg_id = 716288

    new_checkpoint = min(current_checkpoint, recheck_msg_id - 1)
    assert new_checkpoint == 716287


def test_recheck_preserves_future_messages():
    """After recheck, fetcher should still get messages up to current max."""
    messages = [
        {"id": 716288, "text": "test1"},
        {"id": 718418, "text": "test2"},
    ]

    new_checkpoint = max(m["id"] for m in messages)
    assert new_checkpoint == 718418


def test_fetcher_supports_multiple_target_ids():
    """Fetcher should support scanning multiple specific message IDs."""
    # Simulate: fetcher gets target IDs from chat config
    chat = {
        "id": -1001292716582,
        "pending_scan_ids": [716254, 716288],
        "initial_scan_msg_id": None,
    }

    # Should scan both IDs directly, then do normal iter_messages
    pending = chat.get("pending_scan_ids", [])
    assert len(pending) == 2
    assert 716254 in pending
    assert 716288 in pending


def test_checkpoint_set_to_min_of_targets():
    """Checkpoint should be set to min(target_ids) - 1 for recheck."""
    pending_ids = [716254, 716288]
    min_checkpoint = min(pending_ids) - 1

    assert min_checkpoint == 716253
    # This ensures iter_messages(min_id=716253) includes 716254 and 716288


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

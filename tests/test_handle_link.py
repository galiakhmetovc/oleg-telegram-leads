
"""
Tests for handle_link + _add_chat
"""

import sys
import os
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.pipeline import Pipeline, TG_LINK_RE


def test_tg_link_regex():
    match = TG_LINK_RE.search("https://t.me/chat_mila_kolpakova/716254")
    assert match is not None
    assert match.group(1) == "chat_mila_kolpakova"
    assert match.group(2) == "716254"
    print("  ✅ Regex: OK")


async def test_add_chat_with_int_chat_id():
    bot = AsyncMock()
    userbot = AsyncMock()
    entity = MagicMock()
    entity.username = None
    entity.title = "Test Chat"
    entity.id = 1292716582
    userbot.get_entity = AsyncMock(return_value=entity)
    fetcher_mock = AsyncMock()
    fetcher_mock.check_chat_access = AsyncMock(return_value={"ok": True})
    with patch("src.pipeline.config") as mock_config:
        mock_config.load_chats.return_value = []
        mock_config.load_checkpoints.return_value = {}
        mock_config.save_checkpoints = MagicMock()
        mock_config.save_chats = MagicMock()
        mock_config.DATA_DIR = "/tmp/test_leads"
        with patch("src.pipeline.Fetcher", return_value=fetcher_mock):
            with patch("src.pipeline.KeywordScanner"):
                with patch("src.pipeline.AIAnalyzer"):
                    with patch("src.pipeline.Notifier"):
                        pipeline = Pipeline(bot, userbot)
                        event = MagicMock()
                        event.chat_id = -1003996729093
                        try:
                            await pipeline._add_chat(
                                event, chat_id=-1001292716582,
                                chat_title="Chat", username="user",
                                checkpoint_msg_id=716254,
                            )
                            error = None
                        except TypeError as e:
                            error = str(e)
                        assert error is None, f"_add_chat crashed: {error}"
                        print("  ✅ _add_chat int chat_id: OK")


async def test_handle_link_full_flow():
    bot = AsyncMock()
    userbot = AsyncMock()
    entity = MagicMock()
    entity.__class__.__name__ = "Channel"
    entity.id = 1292716582
    entity.title = "Chat"
    entity.username = "chat_mila_kolpakova"
    entity.left = False
    userbot.get_entity = AsyncMock(return_value=entity)
    fetcher_mock = AsyncMock()
    fetcher_mock.check_chat_access = AsyncMock(return_value={"ok": True})
    with patch("src.pipeline.config") as mock_config:
        mock_config.load_chats.return_value = []
        mock_config.load_checkpoints.return_value = {}
        mock_config.save_checkpoints = MagicMock()
        mock_config.save_chats = MagicMock()
        mock_config.DATA_DIR = "/tmp/test_leads"
        with patch("src.pipeline.Fetcher", return_value=fetcher_mock):
            with patch("src.pipeline.KeywordScanner"):
                with patch("src.pipeline.AIAnalyzer"):
                    with patch("src.pipeline.Notifier"):
                        pipeline = Pipeline(bot, userbot)
                        event = MagicMock()
                        event.chat_id = -1003996729093
                        try:
                            await pipeline.handle_link(event, "https://t.me/chat_mila_kolpakova/716254")
                            error = None
                        except TypeError as e:
                            error = str(e)
                        assert error is None, f"handle_link crashed: {error}"
                        print(f"  ✅ handle_link full flow: OK")


async def test_handle_link_existing_chat():
    bot = AsyncMock()
    userbot = AsyncMock()
    entity = MagicMock()
    entity.__class__.__name__ = "Channel"
    entity.id = 1292716582
    entity.title = "Chat"
    entity.username = "chat_mila_kolpakova"
    userbot.get_entity = AsyncMock(return_value=entity)
    msg_mock = MagicMock()
    msg_mock.text = "Поделитесь, какие домофоны ставите?"
    userbot.get_messages = AsyncMock(return_value=msg_mock)
    existing_chat = {"id": -1001292716582, "title": "Chat", "status": "active"}
    with patch("src.pipeline.config") as mock_config:
        mock_config.load_chats.return_value = [existing_chat]
        mock_config.load_checkpoints.return_value = {"-1001292716582": 718380}
        with patch("src.pipeline.KeywordScanner"):
            with patch("src.pipeline.AIAnalyzer"):
                with patch("src.pipeline.Notifier"):
                    pipeline = Pipeline(bot, userbot)
                    event = MagicMock()
                    event.chat_id = -1003996729093
                    try:
                        await pipeline.handle_link(event, "https://t.me/chat_mila_kolpakova/716254")
                        error = None
                    except TypeError as e:
                        error = str(e)
                    assert error is None, f"handle_link (existing) crashed: {error}"
                    print("  ✅ handle_link existing chat: OK")


async def test_add_chat_not_ok():
    bot = AsyncMock()
    userbot = AsyncMock()
    entity = MagicMock()
    entity.username = None
    userbot.get_entity = AsyncMock(return_value=entity)
    fetcher_mock = AsyncMock()
    fetcher_mock.check_chat_access = AsyncMock(return_value={
        "ok": False, "reason": "not_joined", "message": "Test"
    })
    with patch("src.pipeline.config") as mock_config:
        mock_config.load_chats.return_value = []
        mock_config.load_checkpoints.return_value = {}
        mock_config.save_checkpoints = MagicMock()
        mock_config.save_chats = MagicMock()
        mock_config.DATA_DIR = "/tmp/test_leads"
        with patch("src.pipeline.Fetcher", return_value=fetcher_mock):
            with patch("src.pipeline.KeywordScanner"):
                with patch("src.pipeline.AIAnalyzer"):
                    with patch("src.pipeline.Notifier"):
                        pipeline = Pipeline(bot, userbot)
                        event = MagicMock()
                        event.chat_id = -1003996729093
                        try:
                            await pipeline._add_chat(
                                event, chat_id=-1001292716582,
                                chat_title="Chat", username="user",
                                checkpoint_msg_id=716254,
                            )
                            error = None
                        except TypeError as e:
                            error = str(e)
                        assert error is None, f"_add_chat (not ok) crashed: {error}"
                        print("  ✅ _add_chat not-ok: OK")


async def main():
    print("=" * 50)
    print("HANDLE_LINK / ADD_CHAT TESTS")
    print("=" * 50)
    tests = [test_tg_link_regex, test_add_chat_with_int_chat_id, test_handle_link_full_flow, test_handle_link_existing_chat, test_add_chat_not_ok]
    passed = 0
    failed = 0
    for test_fn in tests:
        name = test_fn.__name__
        try:
            result = test_fn()
            if asyncio.iscoroutine(result):
                await result
            passed += 1
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(main())

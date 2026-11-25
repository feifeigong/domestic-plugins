"""Exercise the MCP tools with IMAP wire responses and no real account."""

from __future__ import annotations

import imaplib
import json
import os
from datetime import date, datetime, timezone
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime
from pathlib import Path
import re
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


PLUGIN = Path(__file__).resolve().parents[1]
SERVER = runpy.run_path(str(PLUGIN / "src/china_email_mcp.py"))
DEFAULT_INTERNAL_DATE = date(2026, 11, 2)
DEFAULT_HEADER_DATE = datetime(2026, 11, 2, 8, tzinfo=timezone.utc)
SENT_NAME = "&XfJT0ZAB-"
LISTING = [
    r'(\HasNoChildren) "/" INBOX',
    r'(\HasNoChildren) "/" Sent',
    rf'(\Sent \HasNoChildren) "/" {SENT_NAME}',
    r'(\Noselect \Sent) "/" "Shared"',
    r'(\Drafts \HasNoChildren) "/" "Draft Copies"',
]


class ImapPeer:
    def __init__(self, fixture):
        self.fixture = fixture
        self.data = bytearray()
        self.mailbox = None
        self.append = None
        self.reply("* OK Synthetic IMAP server")

    def makefile(self, _mode):
        return self

    def read(self, size):
        chunk = bytes(self.data[:size])
        del self.data[:size]
        return chunk

    def readline(self, limit):
        return self.read(min(self.data.index(b"\n") + 1, limit)) if self.data else b""

    def close(self):
        pass

    def shutdown(self, _mode):
        pass

    def reply(self, line):
        self.data.extend(line.encode("ascii") + b"\r\n")

    def sendall(self, data):
        if self.append:
            tag, length = self.append
            if length is not None:
                if len(data) != length:
                    raise AssertionError("Unexpected APPEND literal length")
                self.fixture.appended.append(data)
                self.append = (tag, None)
            else:
                if data != b"\r\n":
                    raise AssertionError("Expected APPEND literal terminator")
                self.reply(f"{tag} OK [APPENDUID 77 999] APPEND done")
                self.append = None
            return

        line = data.decode("ascii").rstrip("\r\n")
        self.fixture.commands.append(line.split(" ", 1)[-1])
        tag, command, *rest = line.split(" ", 2)
        args = rest[0] if rest else ""
        if command == "CAPABILITY":
            capabilities = "IMAP4rev1 SPECIAL-USE" if self.fixture.special_use else "IMAP4rev1"
            self.reply(f"* CAPABILITY {capabilities}")
        elif command in {"LOGIN", "ID"}:
            pass
        elif command == "LIST":
            if "RETURN (SPECIAL-USE)" in args and self.fixture.reject_extended:
                self.reply(f"{tag} BAD LIST extension rejected")
                return
            for entry in self.fixture.listing:
                if isinstance(entry, tuple):
                    prefix, name = entry
                    self.reply(f"* LIST {prefix} {{{len(name)}}}")
                    self.data.extend(name + b"\r\n")
                else:
                    self.reply(f"* LIST {entry}")
        elif command == "EXAMINE":
            self.mailbox = SERVER["unquote_imap"](args)
            if self.mailbox not in self.fixture.folders:
                self.reply(f"{tag} NO No such mailbox")
                return
            if not self.fixture.omit_exists:
                self.reply(f"* {len(self.fixture.folders[self.mailbox])} EXISTS")
            if self.fixture.uid_validity is not None:
                self.reply(f"* OK [UIDVALIDITY {self.fixture.uid_validity}] UIDs valid")
            self.reply(f"{tag} OK [READ-ONLY] EXAMINE done")
            return
        elif command == "UID" and args.startswith("SEARCH "):
            if self.fixture.reject_search:
                self.reply(f"{tag} NO IMAP search forbidden")
                return
            uids = list(self.fixture.folders[self.mailbox])
            if self.fixture.empty_search or "UNSEEN" in args:
                uids = []
            hidden = self.fixture.hidden_search_uids.get(self.mailbox, ())
            uids = [uid for uid in uids if uid not in hidden]
            for key, value in re.findall(r"\b(SENTSINCE|SENTBEFORE|SINCE|BEFORE) (\d{1,2}-[A-Za-z]{3}-\d{4})\b", args):
                boundary = datetime.strptime(value, "%d-%b-%Y").date()
                if key.startswith("SENT"):
                    message_dates = [
                        (uid, self.fixture.header_dates.get((self.mailbox, uid), DEFAULT_HEADER_DATE).date())
                        for uid in uids
                    ]
                else:
                    message_dates = [
                        (uid, self.fixture.internal_dates.get((self.mailbox, uid), DEFAULT_INTERNAL_DATE))
                        for uid in uids
                    ]
                if key.endswith("SINCE"):
                    uids = [uid for uid, value in message_dates if value >= boundary]
                else:
                    uids = [uid for uid, value in message_dates if value < boundary]
            cutoff = re.search(r"\bUID 1:(\d+)$", args)
            if cutoff and not self.fixture.ignore_cutoff:
                uids = [uid for uid in uids if uid <= int(cutoff[1])]
            if self.fixture.unordered_search and len(uids) >= 3:
                self.reply(f"* SEARCH {uids[-1]} {uids[0]}")
                uids.pop()
            self.reply("* SEARCH" + (f" {' '.join(map(str, uids))}" if uids else ""))
        elif command == "UID" and args.startswith("FETCH "):
            uid = int(args.split()[1])
            failure = self.fixture.fetch_failures.get((self.mailbox, uid))
            if failure == "full header only" and "HEADER.FIELDS" in args:
                failure = None
            if failure or uid not in self.fixture.folders[self.mailbox]:
                if failure == "no":
                    self.reply(f"{tag} NO Temporary fetch error")
                else:
                    self.reply(f"{tag} OK No literal returned")
                return
            message = EmailMessage(policy=SMTP)
            message["Subject"] = f"{self.mailbox} mail #{uid:04d}"
            message["From"] = "sender@example.test"
            message["To"] = "receiver@example.test"
            message["Date"] = format_datetime(self.fixture.header_dates.get((self.mailbox, uid), DEFAULT_HEADER_DATE))
            message.set_content(f"body marker {uid:04d}")
            if uid == 1:
                message.add_attachment(b"attachment bytes", maintype="application", subtype="octet-stream", filename="test.bin")
            if "BODY.PEEK[HEADER" in args:
                payload = message.as_bytes().split(b"\r\n\r\n", 1)[0] + b"\r\n\r\n"
                section = "FLAGS () RFC822.SIZE 123 BODY[HEADER]"
            else:
                if self.fixture.fail_body:
                    self.reply(f"{tag} NO Body unavailable")
                    return
                payload, section = message.as_bytes(), "BODY[]"
            self.reply(f"* 1 FETCH (UID {uid} {section} {{{len(payload)}}}")
            self.data.extend(payload)
            self.reply(")")
        elif command == "APPEND":
            length = re.search(r"\{(\d+)\}$", args)
            self.append = (tag, int(length[1]))
            self.reply("+ Send literal")
            return
        elif command == "LOGOUT":
            self.reply("* BYE")
        else:
            raise AssertionError(f"Unexpected IMAP command {line}")
        self.reply(f"{tag} OK {command} done")


class MailboxReadingTests(unittest.TestCase):
    def setUp(self):
        self.folders = {
            "INBOX": range(1, 151),
            "Sent": range(1, 4),
            SENT_NAME: range(1, 71),
            "Archive": range(1, 607, 2),
            "Empty": [],
        }
        self.listing = LISTING.copy()
        self.special_use = True
        self.reject_extended = self.reject_search = self.empty_search = self.ignore_cutoff = False
        self.omit_exists = self.unordered_search = self.fail_body = False
        self.uid_validity = 77
        self.fetch_failures = {}
        self.hidden_search_uids = {}
        self.internal_dates = {}
        self.header_dates = {}
        self.commands = []
        self.appended = []
        self.account = {
            "name": "test-mailbox",
            "provider": "custom",
            "email": "account@example.test",
            "password": "placeholder",
            "imap": {"host": "imap.example.test", "port": 143, "secure": False},
            "smtp": {"host": "smtp.example.test", "port": 25, "secure": False},
        }
        env = {key: value for key, value in os.environ.items() if not key.startswith("CHINA_EMAIL_")}
        env["CHINA_EMAIL_ACCOUNTS_JSON"] = json.dumps({"accounts": [self.account]})
        self.enterContext(patch.dict(os.environ, env, clear=True))
        self.enterContext(patch.object(imaplib.IMAP4, "_create_socket", side_effect=lambda _timeout: ImapPeer(self)))

    def request(self, method, params=None):
        return SERVER["handle_request"]({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})["result"]

    def tool(self, name, **arguments):
        return self.request("tools/call", {"name": f"china_email_{name}", "arguments": arguments})

    def ok(self, name, **arguments):
        result = self.tool(name, **arguments)
        self.assertFalse(result.get("isError"), result)
        return result["structuredContent"]

    def error(self, name, expected, **arguments):
        result = self.tool(name, **arguments)
        self.assertTrue(result.get("isError"), result)
        self.assertIn(expected, result["content"][0]["text"])

    def next_page(self, page, **arguments):
        return self.ok(
            "search_messages",
            account=page["account"]["name"],
            mailbox=page["mailbox"],
            before_uid=page["next_before_uid"],
            uid_validity=page["uid_validity"],
            **arguments,
        )

    def test_tools_and_manifest_version(self):
        manifest = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], self.request("initialize")["serverInfo"]["version"])
        tools = {tool["name"]: tool["inputSchema"] for tool in self.request("tools/list")["tools"]}
        self.assertIn("china_email_list_mailboxes", tools)
        self.assertIn("before_uid", tools["china_email_search_messages"]["properties"])

    def test_stdio_protocol_stays_utf8_with_non_utf8_python_io_default(self):
        unknown_tool = "\u56fd\u5185\u90ae\u7bb1"
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": unknown_tool}}
        completed = subprocess.run(
            [sys.executable, str(PLUGIN / "src/china_email_mcp.py")],
            input=(json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"),
            capture_output=True,
            env={**os.environ, "PYTHONIOENCODING": "cp1252"},
            check=True,
            timeout=15,
        )
        result = json.loads(completed.stdout.decode("utf-8"))["result"]
        self.assertIn(unknown_tool, result["content"][0]["text"])

    def test_default_inbox_unfiltered(self):
        page = self.ok("search_messages")
        self.assertEqual(page["mailbox"], "INBOX")
        self.assertEqual(page["mailbox_message_count"], 150)
        self.assertEqual(page["candidate_count"], 150)
        self.assertEqual(page["scanned_count"], 10)
        self.assertEqual(page["status"], "ok")
        self.assertFalse(page["imap_count_mismatch"])
        self.assertEqual([int(mail["uid"]) for mail in page["messages"]], list(range(150, 140, -1)))
        self.assertIn("EXAMINE INBOX", self.commands)

    def test_server_flag_beats_wrong_existing_sent_folder(self):
        page = self.ok("search_messages", mailbox_role="sent", limit=30)
        self.assertEqual(page["mailbox"], SENT_NAME)
        self.assertEqual(page["mailbox_message_count"], 70)
        self.assertEqual(len(page["messages"]), 30)
        self.assertIn('LIST "" "*" RETURN (SPECIAL-USE)', self.commands)
        self.assertEqual(self.ok("search_messages", mailbox="Sent")["mailbox_message_count"], 3)

    def test_chinese_display_name_resolves_to_legacy_wire_name(self):
        page = self.ok("search_messages", mailbox="\u5df2\u53d1\u9001")
        self.assertEqual(page["mailbox_message_count"], 70)
        self.assertIn(f"EXAMINE {SENT_NAME}", self.commands)

    def test_localized_sent_fallback_and_listing_after_extended_list_rejected(self):
        self.reject_extended = True
        self.listing = [rf'(\HasNoChildren) "/" "{SENT_NAME}"', r'(\Noselect) "/" "Sent"']
        page = self.ok("search_messages", mailbox_role="sent")
        self.assertEqual(page["mailbox"], SENT_NAME)
        self.assertIn('LIST "" *', self.commands)
        folders = self.ok("list_mailboxes")["mailboxes"]
        self.assertEqual(folders[0]["display_name"], "\u5df2\u53d1\u9001")
        self.assertFalse(folders[1]["selectable"])

    def test_list_literals_quoted_names_and_nested_sent(self):
        self.special_use = False
        self.listing = [(r'(\HasNoChildren) "."', b"INBOX.Sent Items"), r'(\Noselect) NIL "A\" Folder"']
        self.folders["INBOX.Sent Items"] = [19]
        folders = self.ok("list_mailboxes")["mailboxes"]
        self.assertEqual([folder["name"] for folder in folders], ["INBOX.Sent Items", 'A" Folder'])
        self.assertEqual(self.ok("search_messages", mailbox_role="sent")["messages"][0]["uid"], "19")

    def test_ambiguous_or_unrecognized_sent_is_explicit(self):
        self.listing = [r'() "/" "Sent Items"', r'() "/" Sent']
        self.error("search_messages", "Multiple possible Sent", mailbox_role="sent")
        self.listing = [r'() "/" Outbox']
        self.error("search_messages", "Could not identify", mailbox_role="sent")

    def test_full_pagination_with_no_gaps_and_unordered_duplicate_uids(self):
        self.unordered_search = True
        page = self.ok("search_messages", mailbox_role="sent", limit=50)
        self.assertTrue(page["has_more"])
        self.assertEqual(page["next_before_uid"], 21)
        next_page = self.next_page(page, limit=50)
        self.assertFalse(next_page["has_more"])
        self.assertIsNone(next_page["next_before_uid"])
        uids = [int(item["uid"]) for item in page["messages"] + next_page["messages"]]
        self.assertEqual(uids, list(range(70, 0, -1)))

    def test_inclusive_date_range_and_exclusive_before_through_pagination(self):
        self.folders["INBOX"] = [1, 2, 3, 4]
        self.internal_dates = {
            ("INBOX", 1): date(2026, 8, 31),
            ("INBOX", 2): date(2026, 9, 1),
            ("INBOX", 3): date(2026, 9, 30),
            ("INBOX", 4): date(2026, 10, 1),
        }
        query = {"since": "2026-09-01", "through": "2026-09-30"}
        page = self.ok("search_messages", query=query, limit=1)
        self.assertEqual(page["date_field"], "received")
        self.assertEqual(page["candidate_count"], 2)
        self.assertEqual([item["uid"] for item in page["messages"]], ["3"])
        self.assertTrue(page["has_more"])
        self.assertIn("UID SEARCH ALL SINCE 01-Sep-2026 BEFORE 01-Oct-2026", self.commands)
        older = self.next_page(page, query=query, limit=1)
        self.assertEqual([item["uid"] for item in older["messages"]], ["2"])
        self.assertFalse(older["has_more"])
        self.assertIn("UID SEARCH ALL SINCE 01-Sep-2026 BEFORE 01-Oct-2026 UID 1:2", self.commands)
        equivalent = self.ok("search_messages", query={"since": "2026-09-01", "before": "2026-10-01"})
        self.assertEqual([item["uid"] for item in equivalent["messages"]], ["3", "2"])
        excluded = self.ok("search_messages", query={"since": "2026-09-01", "before": "2026-09-30"})
        self.assertEqual([item["uid"] for item in excluded["messages"]], ["2"])

    def test_sent_date_and_received_date_are_distinct(self):
        self.folders[SENT_NAME] = [1, 2]
        self.internal_dates[(SENT_NAME, 1)] = date(2026, 10, 1)
        self.internal_dates[(SENT_NAME, 2)] = date(2026, 9, 30)
        self.header_dates[(SENT_NAME, 1)] = datetime(2026, 9, 30, 23, 59, tzinfo=timezone.utc)
        self.header_dates[(SENT_NAME, 2)] = datetime(2026, 10, 1, 0, 1, tzinfo=timezone.utc)
        dates = {"since": "2026-09-01", "through": "2026-09-30"}
        sent = self.ok("search_messages", mailbox_role="sent", query={**dates, "date_field": "sent"})
        self.assertEqual(sent["date_field"], "sent")
        self.assertEqual([item["uid"] for item in sent["messages"]], ["1"])
        self.assertEqual(sent["messages"][0]["date"], "2026-09-30T23:59:00+00:00")
        self.assertIn("UID SEARCH ALL SENTSINCE 01-Sep-2026 SENTBEFORE 01-Oct-2026", self.commands)
        received = self.ok("search_messages", mailbox_role="sent", query={**dates, "date_field": "received"})
        self.assertEqual([item["uid"] for item in received["messages"]], ["2"])

    def test_invalid_or_conflicting_date_arguments(self):
        cases = (
            ({"through": "2026-09-30", "before": "2026-10-01"}, "through"),
            ({"through": "2026-09-31"}, "through"),
            ({"through": "9999-12-31"}, "through"),
            ({"since": "2026-10-01", "through": "2026-09-30"}, "since"),
            ({"since": "2026-10-02", "before": "2026-10-01"}, "since"),
            ({"since": "2026-09"}, "since"),
            ({"date_field": "header"}, "date_field"),
        )
        for query, expected_error in cases:
            with self.subTest(query=query):
                self.error("search_messages", expected_error, query=query)
        self.assertFalse(any("UID SEARCH" in command for command in self.commands))

    def test_archive_requires_an_explicit_mailbox_scope(self):
        self.folders["Archive"] = [1]
        self.listing.append(r'(\Archive \HasNoChildren) "/" Archive')
        self.internal_dates[("Archive", 1)] = date(2026, 9, 30)
        query = {"since": "2026-09-01", "through": "2026-09-30"}
        inbox = self.ok("search_messages", query=query)
        self.assertEqual(inbox["mailbox"], "INBOX")
        self.assertEqual(inbox["candidate_count"], 0)
        listed = self.ok("list_mailboxes")["mailboxes"]
        archive = next(folder for folder in listed if folder["name"] == "Archive")
        self.assertTrue(archive["selectable"])
        archived = self.ok("search_messages", mailbox=archive["name"], query=query)
        self.assertEqual(archived["candidate_count"], 1)
        self.assertEqual(archived["messages"][0]["uid"], "1")

    def test_cursor_advances_even_if_server_ignores_uid_range(self):
        self.ignore_cutoff = True
        page = self.ok("search_messages", mailbox="Archive", scan_limit=7, limit=50)
        next_page = self.next_page(page, scan_limit=7, limit=50)
        self.assertTrue(all(int(item["uid"]) < page["next_before_uid"] for item in next_page["messages"]))
        self.assertEqual(next_page["next_before_uid"], 579)

    def test_cursor_validation_and_uidvalidity_reset(self):
        for invalid in (0, -1, 2**32, "1:*", True):
            with self.subTest(invalid=invalid):
                self.error("search_messages", "before_uid must", before_uid=invalid)
        self.error("search_messages", "UIDVALIDITY changed", before_uid=10, uid_validity=76)
        self.error("read_message", "UIDVALIDITY changed", uid="1", uid_validity=76)
        page = self.ok("search_messages", before_uid=1, uid_validity=77)
        self.assertEqual(page["candidate_count"], 0)
        self.assertFalse(page["has_more"])
        self.assertFalse(any("UID SEARCH" in command for command in self.commands))

    def test_empty_search_page_can_find_an_older_result(self):
        args = {"query": {"subject": "INBOX mail #0007"}, "scan_limit": 100}
        page = self.ok("search_messages", **args)
        self.assertEqual(page["status"], "scan_incomplete")
        self.assertEqual(page["messages"], [])
        self.assertEqual(page["next_before_uid"], 51)
        next_page = self.next_page(page, **args)
        self.assertEqual(next_page["status"], "ok")
        self.assertEqual([item["uid"] for item in next_page["messages"]], ["7"])

    def test_search_finds_messages_older_than_maximum_single_page_scan(self):
        self.folders["Archive"] = range(1, 551)
        args = {"query": {"subject": "Archive mail #0001"}, "scan_limit": 500}
        page = self.ok("search_messages", mailbox="Archive", **args)
        self.assertEqual(page["scanned_count"], 500)
        self.assertEqual(page["status"], "scan_incomplete")
        self.assertEqual(page["next_before_uid"], 51)
        older = self.next_page(page, **args)
        self.assertFalse(older["has_more"])
        self.assertEqual([mail["uid"] for mail in older["messages"]], ["1"])

    def test_real_empty_and_filtered_no_match_are_distinct(self):
        empty = self.ok("search_messages", mailbox="Empty")
        self.assertEqual(empty["status"], "empty_mailbox")
        self.assertEqual(empty["mailbox_message_count"], 0)
        unread = self.ok("search_messages", query={"unread": True})
        self.assertEqual(unread["status"], "no_match")
        self.assertEqual(unread["mailbox_message_count"], 150)
        self.assertEqual(unread["candidate_count"], 0)

    def test_positive_or_missing_count_with_empty_unfiltered_search(self):
        self.empty_search = True
        self.assertEqual(self.ok("search_messages")["status"], "imap_visibility_unknown")
        self.omit_exists = True
        page = self.ok("search_messages")
        self.assertIsNone(page["mailbox_message_count"])
        self.assertEqual(page["status"], "imap_visibility_unknown")

    def test_imap_count_mismatch_only_for_initial_imap_search_all(self):
        self.folders["INBOX"] = [1, 2, 3]
        self.hidden_search_uids["INBOX"] = {1}
        page = self.ok("search_messages", limit=1)
        self.assertEqual(page["status"], "ok")
        self.assertEqual(page["mailbox_message_count"], 3)
        self.assertEqual(page["candidate_count"], 2)
        self.assertTrue(page["imap_count_mismatch"])
        next_page = self.next_page(page, limit=1)
        self.assertFalse(next_page["imap_count_mismatch"])
        filtered = self.ok("search_messages", query={"since": "2026-11-02"})
        self.assertFalse(filtered["imap_count_mismatch"])
        filtered_by_subject = self.ok("search_messages", query={"subject": "INBOX mail"})
        self.assertTrue(filtered_by_subject["imap_count_mismatch"])
        self.omit_exists = True
        self.assertFalse(self.ok("search_messages")["imap_count_mismatch"])

    def test_all_header_failures_stay_visible(self):
        self.folders["INBOX"] = [9, 10]
        self.fetch_failures = {("INBOX", 9): "no literal", ("INBOX", 10): "no"}
        page = self.ok("search_messages")
        self.assertEqual(page["status"], "read_failed")
        self.assertEqual(page["mailbox_message_count"], 2)
        self.assertEqual(page["failed_count"], 2)
        self.assertEqual(page["messages"], [])
        self.assertEqual([err["uid"] for err in page["read_errors"]], ["10", "9"])

    def test_partial_failure_preserves_valid_results_and_cursor(self):
        self.fetch_failures[("INBOX", 150)] = "no"
        page = self.ok("search_messages", limit=2)
        self.assertEqual(page["status"], "partial_read")
        self.assertEqual(page["failed_count"], 1)
        self.assertEqual([item["uid"] for item in page["messages"]], ["149", "148"])
        self.assertEqual(page["next_before_uid"], 148)

    def test_failed_full_header_recovers_with_standard_header_subset(self):
        self.fetch_failures[("INBOX", 150)] = "full header only"
        page = self.ok("search_messages", limit=1)
        self.assertEqual(page["status"], "ok")
        self.assertEqual(page["failed_count"], 0)
        self.assertEqual(page["messages"][0]["uid"], "150")
        self.assertTrue(any("HEADER.FIELDS" in command for command in self.commands))

    def test_body_search_and_failed_body_fetch(self):
        page = self.ok("search_messages", query={"text": "body marker 0150"}, scan_limit=2)
        self.assertEqual([item["uid"] for item in page["messages"]], ["150"])
        self.fail_body = True
        page = self.ok("search_messages", query={"text": "body marker"}, scan_limit=2)
        self.assertEqual(page["status"], "read_failed")
        self.assertEqual(page["failed_count"], 2)

    def test_connection_and_read_use_resolved_folder(self):
        connection = self.ok("test_connection", mailbox_role="sent")
        self.assertEqual(connection["imap_mailbox"], {"name": SENT_NAME, "message_count": 70})
        self.assertEqual(connection["checks"]["imap"], "ok")
        kwargs = {"mailbox": SENT_NAME, "uid": "1", "uid_validity": 77}
        mail = self.ok("read_message", **kwargs)
        self.assertEqual(mail["subject"], f"{SENT_NAME} mail #0001")
        self.assertEqual(self.ok("read_message", uid="1")["subject"], "INBOX mail #0001")
        with tempfile.TemporaryDirectory() as folder:
            payload = self.ok("save_attachments", output_dir=folder, **kwargs)
            self.assertEqual(Path(payload["saved"][0]["path"]).read_bytes(), b"attachment bytes")

    def test_wrong_mailbox_and_search_errors_remain_errors(self):
        self.error("search_messages", "No such mailbox", mailbox="Unknown")
        self.error("search_messages", "Specify mailbox or mailbox_role", mailbox="INBOX", mailbox_role="sent")
        self.error("read_message", "uid must be", uid="1:*")
        self.reject_search = True
        self.error("search_messages", "IMAP search forbidden")

    def test_netease_imap_id_and_draft_append_are_preserved(self):
        self.account["provider"] = "163"
        with patch.dict(os.environ, {"CHINA_EMAIL_ACCOUNTS_JSON": json.dumps({"accounts": [self.account]})}):
            self.assertEqual(self.ok("search_messages", limit=1)["status"], "ok")
            draft = self.ok("create_draft", to="recipient@example.test", subject="Test", text="Draft body")
        self.assertTrue(any(command.startswith("ID (") for command in self.commands))
        self.assertTrue(any(command.startswith('APPEND "Draft Copies" ') for command in self.commands))
        self.assertTrue(draft["draft_saved"])
        self.assertIn(b"Draft body", self.appended[0])
        self.assertEqual(SERVER["format_imap_date"](date(2026, 11, 2)), "02-Nov-2026")


if __name__ == "__main__":
    unittest.main()

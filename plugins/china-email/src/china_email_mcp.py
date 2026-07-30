#!/usr/bin/env python3
"""Minimal MCP server for domestic IMAP/SMTP email accounts."""

from __future__ import annotations

import datetime as dt
import email
import email.utils
import html
import http.server
import imaplib
import json
import os
import pathlib
import re
import secrets
import smtplib
import socketserver
import ssl
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser
from email.message import EmailMessage
from email.policy import default
from typing import Any, Callable


SERVER_NAME = "china-email"
SERVER_VERSION = "0.1.0"
DEFAULT_PROTOCOL_VERSION = "2025-06-18"
DEFAULT_CONFIG_RELATIVE_PATH = pathlib.Path(".config") / "china-email" / "accounts.json"
DEFAULT_CONFIG_PATH = pathlib.Path.home() / DEFAULT_CONFIG_RELATIVE_PATH
DEFAULT_CONFIG_DISPLAY_PATH = f"~/{DEFAULT_CONFIG_RELATIVE_PATH.as_posix()}"
DEFAULT_ATTACHMENT_DIR = pathlib.Path.home() / "Downloads" / "china-email-attachments"
MAX_LIMIT = 50
DEFAULT_SCAN_LIMIT = 100
MAX_SCAN_LIMIT = 500
DEFAULT_BODY_CHARS = 12000
MAX_BODY_CHARS = 80000
DEFAULT_SETUP_TTL_SECONDS = 900
NETEASE_PROVIDERS = {"163", "126", "yeah"}
NETEASE_IMAP_HOSTS = {"imap.163.com", "imap.126.com", "imap.yeah.net"}
IMAP_CLIENT_ID = f'("name" "{SERVER_NAME}" "version" "{SERVER_VERSION}" "vendor" "Codex")'
imaplib.Commands.setdefault("ID", ("AUTH", "SELECTED"))
DRAFT_MAILBOX_CANDIDATES: dict[str, list[str]] = {
    "qq": ["Drafts"],
    "163": ["&g0l6P3ux-", "Drafts"],
    "126": ["&g0l6P3ux-", "Drafts"],
    "yeah": ["&g0l6P3ux-", "Drafts"],
}
COMMON_DRAFT_MAILBOX_CANDIDATES = ["Drafts", "&g0l6P3ux-", "草稿箱", "草稿"]


PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "qq": {
        "label": "QQ邮箱",
        "imap": {"host": "imap.qq.com", "port": 993, "secure": True},
        "smtp": {"host": "smtp.qq.com", "port": 465, "secure": True},
        "auth_note": "Enable IMAP/SMTP and use the QQ Mail authorization code.",
    },
    "163": {
        "label": "网易163邮箱",
        "imap": {"host": "imap.163.com", "port": 993, "secure": True},
        "smtp": {"host": "smtp.163.com", "port": 465, "secure": True},
        "auth_note": "Enable IMAP/SMTP and use the client authorization password.",
    },
    "126": {
        "label": "网易126邮箱",
        "imap": {"host": "imap.126.com", "port": 993, "secure": True},
        "smtp": {"host": "smtp.126.com", "port": 465, "secure": True},
        "auth_note": "Enable IMAP/SMTP and use the client authorization password.",
    },
    "yeah": {
        "label": "网易yeah.net邮箱",
        "imap": {"host": "imap.yeah.net", "port": 993, "secure": True},
        "smtp": {"host": "smtp.yeah.net", "port": 465, "secure": True},
        "auth_note": "Enable IMAP/SMTP and use the client authorization password.",
    },
    "tencent-exmail": {
        "label": "腾讯企业邮箱",
        "imap": {"host": "imap.exmail.qq.com", "port": 993, "secure": True},
        "smtp": {"host": "smtp.exmail.qq.com", "port": 465, "secure": True},
        "auth_note": "Use the enterprise mailbox account password or configured client password.",
    },
    "aliyun-mail": {
        "label": "阿里企业邮箱",
        "imap": {"host": "imap.qiye.aliyun.com", "port": 993, "secure": True},
        "smtp": {"host": "smtp.qiye.aliyun.com", "port": 465, "secure": True},
        "auth_note": "Use the enterprise mailbox account password or configured client password.",
    },
    "139": {
        "label": "139邮箱",
        "imap": {"host": "imap.139.com", "port": 993, "secure": True},
        "smtp": {"host": "smtp.139.com", "port": 465, "secure": True},
        "auth_note": "Enable IMAP/SMTP and use the provider-supported client password.",
    },
}

PROVIDER_SETUP_LINKS: dict[str, str] = {
    "qq": "https://mail.qq.com/",
    "163": "https://mail.163.com/",
    "126": "https://mail.126.com/",
    "yeah": "https://www.yeah.net/",
    "tencent-exmail": "https://exmail.qq.com/",
    "aliyun-mail": "https://qiye.aliyun.com/",
    "139": "https://mail.10086.cn/",
}


class ToolError(Exception):
    """Expected tool-level error to return to the model."""


def eprint(message: str) -> None:
    print(f"[{SERVER_NAME}] {message}", file=sys.stderr, flush=True)


def expand_path(value: str | None) -> pathlib.Path | None:
    if not value:
        return None
    return pathlib.Path(os.path.expandvars(os.path.expanduser(value))).resolve()


def load_json_file(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_raw_accounts() -> tuple[list[dict[str, Any]], str | None]:
    accounts: list[dict[str, Any]] = []
    source: str | None = None

    accounts_json = os.environ.get("CHINA_EMAIL_ACCOUNTS_JSON")
    if accounts_json:
        payload = json.loads(accounts_json)
        accounts = payload.get("accounts", payload) if isinstance(payload, dict) else payload
        source = "CHINA_EMAIL_ACCOUNTS_JSON"
    else:
        config_path = expand_path(os.environ.get("CHINA_EMAIL_CONFIG")) or DEFAULT_CONFIG_PATH
        if config_path.exists():
            payload = load_json_file(config_path)
            accounts = payload.get("accounts", payload) if isinstance(payload, dict) else payload
            source = str(config_path)

    single_email = os.environ.get("CHINA_EMAIL_ADDRESS")
    single_password = os.environ.get("CHINA_EMAIL_PASSWORD") or os.environ.get("CHINA_EMAIL_AUTH_CODE")
    if single_email and single_password:
        accounts.append(
            {
                "name": os.environ.get("CHINA_EMAIL_ACCOUNT_NAME", "default"),
                "provider": os.environ.get("CHINA_EMAIL_PROVIDER", "custom"),
                "email": single_email,
                "username": os.environ.get("CHINA_EMAIL_USERNAME", single_email),
                "password": single_password,
                "imap": {
                    "host": os.environ.get("CHINA_EMAIL_IMAP_HOST"),
                    "port": int(os.environ.get("CHINA_EMAIL_IMAP_PORT", "993")),
                    "secure": env_bool("CHINA_EMAIL_IMAP_SECURE", True),
                },
                "smtp": {
                    "host": os.environ.get("CHINA_EMAIL_SMTP_HOST"),
                    "port": int(os.environ.get("CHINA_EMAIL_SMTP_PORT", "465")),
                    "secure": env_bool("CHINA_EMAIL_SMTP_SECURE", True),
                },
            }
        )
        source = f"{source or ''}+env-single".strip("+")

    if not isinstance(accounts, list):
        raise ToolError("Account configuration must be a JSON array or an object with an accounts array.")
    return accounts, source


def env_bool(name: str, default_value: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default_value
    return raw.lower() in {"1", "true", "yes", "on"}


def normalize_account(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ToolError("Every account entry must be an object.")

    provider = str(raw.get("provider") or "custom").lower()
    preset = PROVIDER_PRESETS.get(provider, {})
    imap_config = {**preset.get("imap", {}), **compact_dict(raw.get("imap") or {})}
    smtp_config = {**preset.get("smtp", {}), **compact_dict(raw.get("smtp") or {})}

    address = raw.get("email") or raw.get("address")
    username = raw.get("username") or raw.get("user") or address
    password = raw.get("password") or raw.get("authCode") or raw.get("authorizationCode")

    if not raw.get("name"):
        raise ToolError("Each account needs a unique name.")
    if not address:
        raise ToolError(f"Account {raw.get('name')} is missing email.")
    if not username:
        raise ToolError(f"Account {raw.get('name')} is missing username.")
    if not password:
        raise ToolError(f"Account {raw.get('name')} is missing password or authorization code.")
    if not imap_config.get("host"):
        raise ToolError(f"Account {raw.get('name')} is missing IMAP host.")
    if not smtp_config.get("host"):
        raise ToolError(f"Account {raw.get('name')} is missing SMTP host.")

    return {
        "name": str(raw["name"]),
        "provider": provider,
        "email": str(address),
        "username": str(username),
        "password": str(password),
        "display_name": raw.get("displayName") or raw.get("display_name"),
        "imap": normalize_endpoint(imap_config, default_port=993),
        "smtp": normalize_endpoint(smtp_config, default_port=465),
    }


def normalize_endpoint(config: dict[str, Any], default_port: int) -> dict[str, Any]:
    return {
        "host": str(config.get("host")),
        "port": int(config.get("port", default_port)),
        "secure": bool(config.get("secure", True)),
    }


def compact_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


def load_accounts() -> tuple[list[dict[str, Any]], str | None]:
    raw_accounts, source = load_raw_accounts()
    names: set[str] = set()
    accounts = []
    for raw in raw_accounts:
        account = normalize_account(raw)
        if account["name"] in names:
            raise ToolError(f"Duplicate account name: {account['name']}")
        names.add(account["name"])
        accounts.append(account)
    return accounts, source


def load_config_payload(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {"accounts": []}
    payload = load_json_file(path)
    if isinstance(payload, list):
        return {"accounts": payload}
    if isinstance(payload, dict):
        accounts = payload.get("accounts", [])
        if not isinstance(accounts, list):
            raise ToolError(f"{path} must contain an accounts array.")
        return payload
    raise ToolError(f"{path} must be a JSON object or array.")


def write_config_payload(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def upsert_raw_account(raw_account: dict[str, Any], path: pathlib.Path = DEFAULT_CONFIG_PATH) -> None:
    normalize_account(raw_account)
    payload = load_config_payload(path)
    accounts = payload.setdefault("accounts", [])
    replaced = False
    for index, existing in enumerate(accounts):
        if isinstance(existing, dict) and existing.get("name") == raw_account["name"]:
            accounts[index] = raw_account
            replaced = True
            break
    if not replaced:
        accounts.append(raw_account)
    write_config_payload(path, payload)


def resolve_account(name: str | None = None) -> dict[str, Any]:
    accounts, _ = load_accounts()
    if not accounts:
        raise ToolError(
            f"No email accounts configured. Create {DEFAULT_CONFIG_DISPLAY_PATH} or set CHINA_EMAIL_* variables."
        )
    if name:
        for account in accounts:
            if account["name"] == name:
                return account
        raise ToolError(f"Unknown account: {name}")
    if len(accounts) == 1:
        return accounts[0]
    available = ", ".join(account["name"] for account in accounts)
    raise ToolError(f"Multiple accounts configured. Specify account. Available accounts: {available}")


def public_account(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": account["name"],
        "provider": account["provider"],
        "email": mask_email(account["email"]),
        "username": mask_email(account["username"]),
        "imap": {k: account["imap"][k] for k in ("host", "port", "secure")},
        "smtp": {k: account["smtp"][k] for k in ("host", "port", "secure")},
    }


def mask_email(value: str) -> str:
    if "@" not in value:
        return "***"
    local, domain = value.split("@", 1)
    if len(local) <= 2:
        masked_local = local[:1] + "*"
    else:
        masked_local = local[:2] + "***" + local[-1:]
    return f"{masked_local}@{domain}"


def connect_imap(account: dict[str, Any]) -> imaplib.IMAP4:
    endpoint = account["imap"]
    if endpoint["secure"]:
        client: imaplib.IMAP4 = imaplib.IMAP4_SSL(endpoint["host"], endpoint["port"], ssl_context=ssl.create_default_context())
    else:
        client = imaplib.IMAP4(endpoint["host"], endpoint["port"])
    client.login(account["username"], account["password"])
    send_imap_id_if_needed(client, account)
    return client


def send_imap_id_if_needed(client: imaplib.IMAP4, account: dict[str, Any]) -> None:
    if not needs_imap_id(account):
        return
    status, response = client._simple_command("ID", IMAP_CLIENT_ID)
    require_ok(status, response, "send IMAP ID")


def needs_imap_id(account: dict[str, Any]) -> bool:
    provider = str(account.get("provider") or "").lower()
    host = str((account.get("imap") or {}).get("host") or "").lower()
    return provider in NETEASE_PROVIDERS or host in NETEASE_IMAP_HOSTS


def connect_smtp(account: dict[str, Any]) -> smtplib.SMTP:
    endpoint = account["smtp"]
    if endpoint["secure"]:
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            endpoint["host"],
            endpoint["port"],
            timeout=30,
            context=ssl.create_default_context(),
        )
    else:
        client = smtplib.SMTP(endpoint["host"], endpoint["port"], timeout=30)
        client.ehlo()
        if client.has_extn("starttls"):
            client.starttls(context=ssl.create_default_context())
    client.login(account["username"], account["password"])
    return client


def require_ok(status: str, response: list[bytes], action: str) -> list[bytes]:
    if status != "OK":
        detail = " ".join(to_text(item) for item in response if item)
        raise ToolError(f"{action} failed: {detail or status}")
    return response


def to_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def parse_date(value: str) -> str:
    parsed = dt.date.fromisoformat(value)
    return parsed.strftime("%d-%b-%Y")


def clamp_int(value: Any, default_value: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default_value
    return max(min_value, min(max_value, parsed))


def extract_uid_list(response: list[bytes]) -> list[str]:
    if not response or not response[0]:
        return []
    return [uid.decode("ascii", errors="ignore") for uid in response[0].split() if uid]


def build_search_criteria(query: dict[str, Any]) -> list[str]:
    criteria = ["ALL"]
    if query.get("unread") is True:
        criteria.append("UNSEEN")
    if query.get("flagged") is True:
        criteria.append("FLAGGED")
    if query.get("since"):
        criteria.extend(["SINCE", parse_date(str(query["since"]))])
    if query.get("before"):
        criteria.extend(["BEFORE", parse_date(str(query["before"]))])
    return criteria


def select_mailbox(client: imaplib.IMAP4, mailbox: str) -> int:
    status, response = client.select(format_mailbox_arg(mailbox), readonly=True)
    require_ok(status, response, f"select mailbox {mailbox}")
    try:
        return int(response[0] or 0)
    except (TypeError, ValueError):
        return 0


def format_mailbox_arg(mailbox: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9._&+=/-]+", mailbox):
        return mailbox
    escaped = mailbox.replace("\\", "\\\\").replace('"', r"\"")
    return f'"{escaped}"'


def fetch_headers(client: imaplib.IMAP4, uid: str) -> dict[str, Any] | None:
    status, response = client.uid("FETCH", uid, "(UID FLAGS RFC822.SIZE BODY.PEEK[HEADER])")
    if status != "OK":
        return None
    raw_header = find_bytes_payload(response)
    if not raw_header:
        return None
    message = email.message_from_bytes(raw_header, policy=default)
    return {
        "uid": uid,
        "subject": str(message.get("subject", "")),
        "from": address_list(message.get_all("from", [])),
        "to": address_list(message.get_all("to", [])),
        "cc": address_list(message.get_all("cc", [])),
        "date": normalize_message_date(message.get("date")),
        "message_id": str(message.get("message-id", "")),
        "flags": extract_flags(response),
        "size": extract_size(response),
    }


def find_bytes_payload(response: list[Any]) -> bytes | None:
    for item in response:
        if isinstance(item, tuple):
            for part in item:
                if isinstance(part, bytes) and b"\r\n" in part:
                    return part
        elif isinstance(item, bytes) and b"\r\n" in item:
            return item
    return None


def extract_flags(response: list[Any]) -> list[str]:
    text = " ".join(to_text(item[0] if isinstance(item, tuple) else item) for item in response if item)
    match = re.search(r"FLAGS \((.*?)\)", text)
    if not match:
        return []
    return [flag for flag in match.group(1).split() if flag]


def extract_size(response: list[Any]) -> int | None:
    text = " ".join(to_text(item[0] if isinstance(item, tuple) else item) for item in response if item)
    match = re.search(r"RFC822\.SIZE (\d+)", text)
    return int(match.group(1)) if match else None


def normalize_message_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed:
            return parsed.isoformat()
    except (TypeError, ValueError):
        pass
    return value


def address_list(headers: list[str]) -> list[dict[str, str]]:
    addresses = []
    for display_name, address in email.utils.getaddresses(headers):
        if not address:
            continue
        addresses.append({"name": display_name, "email": address})
    return addresses


def header_text(message: dict[str, Any]) -> str:
    fields: list[str] = [
        message.get("subject", ""),
        " ".join(item.get("email", "") for item in message.get("from", [])),
        " ".join(item.get("email", "") for item in message.get("to", [])),
        " ".join(item.get("email", "") for item in message.get("cc", [])),
    ]
    return "\n".join(fields).lower()


def matches_query(message: dict[str, Any], query: dict[str, Any], body_text: str = "") -> bool:
    def contains(value: Any, haystack: str) -> bool:
        return not value or str(value).lower() in haystack

    sender = " ".join(item.get("email", "") for item in message.get("from", [])).lower()
    recipients = " ".join(item.get("email", "") for item in message.get("to", []) + message.get("cc", [])).lower()
    subject = str(message.get("subject", "")).lower()
    combined = f"{header_text(message)}\n{body_text}".lower()

    return (
        contains(query.get("from"), sender)
        and contains(query.get("to"), recipients)
        and contains(query.get("subject"), subject)
        and contains(query.get("text"), combined)
    )


def fetch_raw_message(client: imaplib.IMAP4, uid: str) -> bytes:
    status, response = client.uid("FETCH", uid, "(BODY.PEEK[])")
    require_ok(status, response, f"fetch message {uid}")
    raw = find_bytes_payload(response)
    if not raw:
        raise ToolError(f"Message {uid} has no fetchable body.")
    return raw


def discover_draft_mailbox(client: imaplib.IMAP4, account: dict[str, Any], requested: str | None = None) -> str:
    if requested:
        return requested

    status, response = client.list()
    require_ok(status, response, "list mailboxes")
    mailboxes: list[str] = []
    for item in response:
        text = to_text(item)
        name = parse_list_mailbox_name(text)
        if not name:
            continue
        mailboxes.append(name)
        if has_imap_list_attribute(text, "\\Drafts"):
            return name

    candidates = DRAFT_MAILBOX_CANDIDATES.get(str(account.get("provider") or "").lower(), []) + COMMON_DRAFT_MAILBOX_CANDIDATES
    for candidate in candidates:
        if candidate in mailboxes:
            return candidate

    for name in mailboxes:
        lowered = name.lower()
        if lowered.endswith("/drafts") or lowered == "drafts" or "draft" in lowered or "草稿" in name:
            return name

    available = ", ".join(mailboxes) or "none"
    raise ToolError(f"Could not find Drafts mailbox. Specify draft_mailbox explicitly. Available mailboxes: {available}")


def parse_list_mailbox_name(value: str) -> str | None:
    match = re.search(r'"((?:[^"\\]|\\.)*)"\s*$', value)
    if match:
        return unescape_imap_quoted(match.group(1))
    match = re.search(r'\)\s+(?:NIL|"[^"]*")\s+(.+)\s*$', value)
    if match:
        return match.group(1).strip()
    return None


def unescape_imap_quoted(value: str) -> str:
    return value.replace(r"\"", '"').replace(r"\\", "\\")


def has_imap_list_attribute(list_line: str, attribute: str) -> bool:
    first_group = list_line.split(")", 1)[0].lower()
    return attribute.lower() in first_group.split()


def append_draft_message(
    client: imaplib.IMAP4,
    account: dict[str, Any],
    message: EmailMessage,
    requested_mailbox: str | None = None,
) -> dict[str, Any]:
    mailbox = discover_draft_mailbox(client, account, requested_mailbox)
    data = message.as_bytes(policy=default.clone(linesep="\r\n"))
    status, response = client.append(format_mailbox_arg(mailbox), r"(\Draft)", None, data)
    require_ok(status, response, f"save draft to {mailbox}")
    return {
        "mailbox": mailbox,
        "uid": extract_append_uid(response),
        "response": [to_text(item) for item in response if item],
    }


def extract_append_uid(response: list[bytes]) -> str | None:
    text = " ".join(to_text(item) for item in response if item)
    match = re.search(r"\[APPENDUID\s+\d+\s+([0-9:,\*]+)\]", text, flags=re.IGNORECASE)
    return match.group(1) if match else None


def message_to_text(message: email.message.EmailMessage) -> tuple[str, str]:
    plain_parts: list[str] = []
    html_parts: list[str] = []

    if message.is_multipart():
        for part in message.walk():
            if part.get_content_disposition() == "attachment":
                continue
            content_type = part.get_content_type()
            if content_type == "text/plain":
                plain_parts.append(safe_get_content(part))
            elif content_type == "text/html":
                html_parts.append(safe_get_content(part))
    else:
        content_type = message.get_content_type()
        if content_type == "text/plain":
            plain_parts.append(safe_get_content(message))
        elif content_type == "text/html":
            html_parts.append(safe_get_content(message))

    plain = "\n\n".join(part.strip() for part in plain_parts if part.strip())
    html_body = "\n\n".join(part.strip() for part in html_parts if part.strip())
    if not plain and html_body:
        plain = html_to_plain_text(html_body)
    return plain, html_body


def safe_get_content(part: email.message.EmailMessage) -> str:
    try:
        content = part.get_content()
    except Exception:
        payload = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        content = payload.decode(charset, errors="replace")
    return str(content)


def html_to_plain_text(value: str) -> str:
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", value)
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"(?i)</p>", "\n\n", value)
    value = re.sub(r"<[^>]+>", "", value)
    return html.unescape(value)


def attachment_summaries(message: email.message.EmailMessage) -> list[dict[str, Any]]:
    attachments = []
    for index, part in enumerate(iter_attachment_parts(message), start=1):
        payload = part.get_payload(decode=True) or b""
        attachments.append(
            {
                "index": index,
                "filename": part.get_filename() or f"attachment-{index}",
                "content_type": part.get_content_type(),
                "size": len(payload),
                "content_id": part.get("content-id", ""),
            }
        )
    return attachments


def iter_attachment_parts(message: email.message.EmailMessage) -> list[email.message.EmailMessage]:
    parts = []
    for part in message.walk():
        filename = part.get_filename()
        disposition = part.get_content_disposition()
        if filename or disposition == "attachment":
            parts.append(part)
    return parts


def truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + f"\n\n[Truncated to {max_chars} characters]"


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", value).strip()
    return cleaned or "attachment"


def ensure_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    raise ToolError("Expected a string or array of strings.")


def html_escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def provider_options(selected: str | None = None) -> str:
    options = []
    for provider, preset in PROVIDER_PRESETS.items():
        is_selected = " selected" if provider == selected else ""
        options.append(
            f'<option value="{html_escape(provider)}"{is_selected}>{html_escape(preset["label"])} ({html_escape(provider)})</option>'
        )
    custom_selected = " selected" if selected == "custom" else ""
    options.append(f'<option value="custom"{custom_selected}>自定义 IMAP/SMTP 邮箱</option>')
    return "\n".join(options)


def setup_links_html() -> str:
    links = []
    for provider, url in PROVIDER_SETUP_LINKS.items():
        label = PROVIDER_PRESETS.get(provider, {}).get("label", provider)
        links.append(f'<a href="{html_escape(url)}" target="_blank" rel="noreferrer">{html_escape(label)}</a>')
    return " ".join(links)


def render_setup_page(token: str, provider: str | None = None, account_name: str | None = None, message: str = "") -> str:
    message_html = f'<div class="notice">{html_escape(message)}</div>' if message else ""
    default_provider = provider or "qq"
    default_name = account_name or default_provider
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>国内邮箱配置向导</title>
  <style>
    :root {{
      color-scheme: light dark;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #101113;
      color: #f7f7f7;
    }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 32px 16px;
      background: #101113;
    }}
    main {{
      width: min(760px, 100%);
      background: #191a1d;
      border: 1px solid #303238;
      border-radius: 12px;
      padding: 28px;
      box-sizing: border-box;
      box-shadow: 0 18px 70px rgba(0, 0, 0, .35);
    }}
    h1 {{
      font-size: 28px;
      line-height: 1.2;
      margin: 0 0 8px;
      letter-spacing: 0;
    }}
    p {{
      color: #b9bbc2;
      line-height: 1.65;
      margin: 0 0 18px;
    }}
    form {{
      display: grid;
      gap: 16px;
    }}
    label {{
      display: grid;
      gap: 8px;
      color: #e8e8ea;
      font-weight: 650;
    }}
    input, select {{
      width: 100%;
      min-height: 44px;
      border-radius: 8px;
      border: 1px solid #3a3d44;
      background: #101113;
      color: #f7f7f7;
      padding: 10px 12px;
      box-sizing: border-box;
      font-size: 15px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }}
    .custom {{
      border: 1px solid #303238;
      border-radius: 10px;
      padding: 16px;
      display: grid;
      gap: 14px;
    }}
    .checks {{
      display: flex;
      gap: 18px;
      flex-wrap: wrap;
      color: #d9dae0;
    }}
    .checks label {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-weight: 500;
    }}
    .checks input {{
      width: auto;
      min-height: auto;
    }}
    button {{
      justify-self: start;
      border: 0;
      border-radius: 8px;
      padding: 12px 18px;
      background: #c2412d;
      color: white;
      font-size: 15px;
      font-weight: 750;
      cursor: pointer;
    }}
    .notice {{
      border: 1px solid #4f7b3f;
      background: #183014;
      color: #dbffd3;
      border-radius: 8px;
      padding: 12px 14px;
      margin: 14px 0 18px;
      line-height: 1.55;
    }}
    .hint {{
      color: #9ea1aa;
      font-size: 13px;
      line-height: 1.55;
      font-weight: 400;
    }}
    .links {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 8px;
    }}
    a {{
      color: #ffb4a7;
      text-decoration: none;
    }}
    @media (max-width: 640px) {{
      main {{ padding: 22px; }}
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>国内邮箱配置向导</h1>
    <p>选择邮箱服务商，填入邮箱地址和客户端授权码。配置会保存在本机 <code>{html_escape(DEFAULT_CONFIG_DISPLAY_PATH)}</code>，不会上传到外部服务。</p>
    {message_html}
    <form method="post" action="/save">
      <input type="hidden" name="token" value="{html_escape(token)}">
      <div class="grid">
        <label>邮箱服务商
          <select name="provider">
            {provider_options(default_provider)}
          </select>
        </label>
        <label>账号名称
          <input name="name" value="{html_escape(default_name)}" placeholder="qq 或 work" required>
          <span class="hint">以后在 Codex 里用这个名字指定邮箱账号。</span>
        </label>
      </div>
      <label>邮箱地址
        <input name="email" type="email" autocomplete="username" placeholder="your-name@qq.com" required>
      </label>
      <label>授权码 / 客户端专用密码
        <input name="password" type="password" autocomplete="current-password" placeholder="不是网页登录密码" required>
        <span class="hint">QQ、网易等邮箱通常要先在网页邮箱设置里开启 IMAP/SMTP，再生成授权码。</span>
      </label>
      <section class="custom">
        <strong>自定义服务器，仅 provider 选 custom 时需要</strong>
        <div class="grid">
          <label>IMAP Host
            <input name="imap_host" placeholder="imap.example.cn">
          </label>
          <label>SMTP Host
            <input name="smtp_host" placeholder="smtp.example.cn">
          </label>
        </div>
        <div class="grid">
          <label>IMAP Port
            <input name="imap_port" type="number" value="993">
          </label>
          <label>SMTP Port
            <input name="smtp_port" type="number" value="465">
          </label>
        </div>
      </section>
      <div class="checks">
        <label><input type="checkbox" name="test_imap" checked> 保存前测试收信连接</label>
        <label><input type="checkbox" name="test_smtp"> 同时测试发信登录</label>
      </div>
      <button type="submit">保存并启用</button>
    </form>
    <p class="hint" style="margin-top: 18px;">常用邮箱入口：<span class="links">{setup_links_html()}</span></p>
  </main>
</body>
</html>"""


def render_result_page(title: str, body: str, ok: bool = True) -> str:
    color = "#183014" if ok else "#351a1a"
    border = "#4f7b3f" if ok else "#8b3a3a"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html_escape(title)}</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
      background: #101113;
      color: #f7f7f7;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(680px, 100%);
      border: 1px solid {border};
      background: {color};
      border-radius: 12px;
      padding: 28px;
      box-sizing: border-box;
      line-height: 1.65;
    }}
    h1 {{ margin: 0 0 10px; font-size: 26px; letter-spacing: 0; }}
    p {{ margin: 0 0 12px; color: #ebecef; }}
    a {{ color: #ffb4a7; }}
  </style>
</head>
<body><main><h1>{html_escape(title)}</h1><p>{html_escape(body)}</p></main></body>
</html>"""


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class SetupWizardHandler(http.server.BaseHTTPRequestHandler):
    server: "SetupWizardHTTPServer"

    def log_message(self, format: str, *args: Any) -> None:
        eprint("setup wizard: " + (format % args))

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/health":
            self.send_text("ok")
            return
        if not self.valid_token(query.get("token", [""])[0]):
            self.send_html(render_result_page("链接已失效", "请回到 Codex 重新打开国内邮箱配置向导。", ok=False), 403)
            return
        self.send_html(
            render_setup_page(
                self.server.token,
                provider=self.server.default_provider,
                account_name=self.server.default_account_name,
            )
        )

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/save":
            self.send_html(render_result_page("路径不存在", "请回到配置向导重新提交。", ok=False), 404)
            return

        length = int(self.headers.get("content-length", "0"))
        payload = self.rfile.read(length).decode("utf-8", errors="replace")
        form = urllib.parse.parse_qs(payload)
        if not self.valid_token(self.first(form, "token")):
            self.send_html(render_result_page("链接已失效", "请回到 Codex 重新打开国内邮箱配置向导。", ok=False), 403)
            return

        try:
            raw_account = self.form_to_account(form)
            account = normalize_account(raw_account)
            checks: list[str] = []
            if "test_imap" in form:
                client = connect_imap(account)
                try:
                    select_mailbox(client, "INBOX")
                    checks.append("IMAP 收信连接通过")
                finally:
                    try:
                        client.logout()
                    except Exception:
                        pass
            if "test_smtp" in form:
                client = connect_smtp(account)
                try:
                    client.noop()
                    checks.append("SMTP 发信登录通过")
                finally:
                    client.quit()
            upsert_raw_account(raw_account, DEFAULT_CONFIG_PATH)
            check_text = "，".join(checks) if checks else "未执行连接测试"
            self.send_html(
                render_result_page(
                    "配置完成",
                    f"账号 {raw_account['name']} 已保存到本机配置。{check_text}。现在可以回到 Codex 让国内邮箱插件列出账号或搜索邮件。",
                    ok=True,
                )
            )
            threading.Thread(target=self.shutdown_later, daemon=True).start()
        except Exception as exc:
            self.send_html(
                render_setup_page(
                    self.server.token,
                    provider=self.first(form, "provider") or self.server.default_provider,
                    account_name=self.first(form, "name") or self.server.default_account_name,
                    message=f"保存失败：{exc}",
                ),
                400,
            )

    def shutdown_later(self) -> None:
        time.sleep(2)
        self.server.shutdown()

    def form_to_account(self, form: dict[str, list[str]]) -> dict[str, Any]:
        provider = self.first(form, "provider") or "custom"
        address = self.first(form, "email")
        raw_account: dict[str, Any] = {
            "name": self.first(form, "name"),
            "provider": provider,
            "email": address,
            "username": address,
            "password": self.first(form, "password"),
        }
        if provider == "custom":
            raw_account["imap"] = {
                "host": self.first(form, "imap_host"),
                "port": int(self.first(form, "imap_port") or "993"),
                "secure": True,
            }
            raw_account["smtp"] = {
                "host": self.first(form, "smtp_host"),
                "port": int(self.first(form, "smtp_port") or "465"),
                "secure": True,
            }
        return raw_account

    def valid_token(self, value: str) -> bool:
        return secrets.compare_digest(value or "", self.server.token)

    def first(self, form: dict[str, list[str]], key: str) -> str:
        values = form.get(key, [])
        return values[0].strip() if values else ""

    def send_html(self, content: str, status: int = 200) -> None:
        data = content.encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_text(self, content: str, status: int = 200) -> None:
        data = content.encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "text/plain; charset=utf-8")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class SetupWizardHTTPServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], token: str, provider: str | None, account_name: str | None):
        super().__init__(address, SetupWizardHandler)
        self.token = token
        self.default_provider = provider
        self.default_account_name = account_name


def create_setup_wizard(
    provider: str | None = None,
    account_name: str | None = None,
    ttl_seconds: int = DEFAULT_SETUP_TTL_SECONDS,
) -> tuple[SetupWizardHTTPServer, str]:
    token = secrets.token_urlsafe(24)
    server = SetupWizardHTTPServer(("127.0.0.1", 0), token, provider, account_name)
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/?token={urllib.parse.quote(token)}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if ttl_seconds > 0:
        threading.Thread(target=shutdown_after_ttl, args=(server, ttl_seconds), daemon=True).start()
    return server, url


def shutdown_after_ttl(server: SetupWizardHTTPServer, ttl_seconds: int) -> None:
    time.sleep(ttl_seconds)
    try:
        server.shutdown()
    except Exception:
        pass


def start_setup_wizard(args: dict[str, Any]) -> dict[str, Any]:
    provider = args.get("provider")
    if provider and provider not in PROVIDER_PRESETS and provider != "custom":
        raise ToolError(f"Unknown provider: {provider}")
    ttl_seconds = clamp_int(args.get("ttl_seconds"), DEFAULT_SETUP_TTL_SECONDS, 60, 3600)
    _, url = create_setup_wizard(
        provider=provider,
        account_name=args.get("account_name"),
        ttl_seconds=ttl_seconds,
    )
    open_browser = args.get("open_browser", True) is not False
    opened = False
    if open_browser:
        try:
            opened = webbrowser.open(url)
        except Exception:
            opened = False
    return tool_result(
        {
            "url": url,
            "opened_browser": opened,
            "expires_in_seconds": ttl_seconds,
            "config_path": str(DEFAULT_CONFIG_PATH),
            "note": "Open this local URL to configure an account without editing JSON. Use a mailbox authorization code or client password.",
        }
    )


def run_setup_wizard_cli() -> None:
    _, url = create_setup_wizard(ttl_seconds=0)
    print(f"China Email setup wizard: {url}", flush=True)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nSetup wizard stopped.", flush=True)


def tool_result(payload: Any) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
        "structuredContent": payload,
    }


def error_result(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def list_providers(_: dict[str, Any]) -> dict[str, Any]:
    providers = []
    for name, preset in PROVIDER_PRESETS.items():
        providers.append(
            {
                "name": name,
                "label": preset["label"],
                "imap": preset["imap"],
                "smtp": preset["smtp"],
                "auth_note": preset["auth_note"],
            }
        )
    return tool_result({"providers": providers})


def list_accounts(_: dict[str, Any]) -> dict[str, Any]:
    accounts, source = load_accounts()
    return tool_result(
        {
            "config_source": source,
            "default_config_path": str(DEFAULT_CONFIG_PATH),
            "accounts": [public_account(account) for account in accounts],
            "setup_hint": "If no accounts are configured, call china_email_start_setup to open the local setup wizard.",
        }
    )


def test_connection(args: dict[str, Any]) -> dict[str, Any]:
    account = resolve_account(args.get("account"))
    checks = {"imap": None, "smtp": None}

    if args.get("check_imap", True):
        client = connect_imap(account)
        try:
            select_mailbox(client, str(args.get("mailbox") or "INBOX"))
            checks["imap"] = "ok"
        finally:
            try:
                client.logout()
            except Exception:
                pass

    if args.get("check_smtp", False):
        client = connect_smtp(account)
        try:
            client.noop()
            checks["smtp"] = "ok"
        finally:
            client.quit()

    return tool_result({"account": public_account(account), "checks": checks})


def search_messages(args: dict[str, Any]) -> dict[str, Any]:
    account = resolve_account(args.get("account"))
    mailbox = str(args.get("mailbox") or "INBOX")
    query = args.get("query") or {}
    if not isinstance(query, dict):
        raise ToolError("query must be an object.")

    limit = clamp_int(args.get("limit"), 10, 1, MAX_LIMIT)
    scan_limit = clamp_int(args.get("scan_limit"), DEFAULT_SCAN_LIMIT, 1, MAX_SCAN_LIMIT)
    criteria = build_search_criteria(query)

    client = connect_imap(account)
    try:
        select_mailbox(client, mailbox)
        status, response = client.uid("SEARCH", None, *criteria)
        require_ok(status, response, "search")
        candidate_uids = extract_uid_list(response)[-scan_limit:]
        messages: list[dict[str, Any]] = []
        for uid in reversed(candidate_uids):
            summary = fetch_headers(client, uid)
            if not summary:
                continue
            body_text = ""
            if query.get("text"):
                raw = fetch_raw_message(client, uid)
                parsed = email.message_from_bytes(raw, policy=default)
                body_text, _ = message_to_text(parsed)
            if matches_query(summary, query, body_text):
                messages.append(summary)
            if len(messages) >= limit:
                break
    finally:
        try:
            client.logout()
        except Exception:
            pass

    return tool_result(
        {
            "account": public_account(account),
            "mailbox": mailbox,
            "criteria": criteria,
            "scan_limit": scan_limit,
            "limit": limit,
            "messages": messages,
        }
    )


def read_message(args: dict[str, Any]) -> dict[str, Any]:
    account = resolve_account(args.get("account"))
    mailbox = str(args.get("mailbox") or "INBOX")
    uid = str(args.get("uid") or "")
    if not uid:
        raise ToolError("uid is required.")
    max_body_chars = clamp_int(args.get("max_body_chars"), DEFAULT_BODY_CHARS, 100, MAX_BODY_CHARS)

    client = connect_imap(account)
    try:
        select_mailbox(client, mailbox)
        raw = fetch_raw_message(client, uid)
    finally:
        try:
            client.logout()
        except Exception:
            pass

    message = email.message_from_bytes(raw, policy=default)
    plain, html_body = message_to_text(message)
    payload = {
        "account": public_account(account),
        "mailbox": mailbox,
        "uid": uid,
        "subject": str(message.get("subject", "")),
        "from": address_list(message.get_all("from", [])),
        "to": address_list(message.get_all("to", [])),
        "cc": address_list(message.get_all("cc", [])),
        "date": normalize_message_date(message.get("date")),
        "message_id": str(message.get("message-id", "")),
        "body_text": truncate(plain, max_body_chars),
        "attachments": attachment_summaries(message),
    }
    if args.get("include_html", False):
        payload["body_html"] = truncate(html_body, max_body_chars)
    return tool_result(payload)


def save_attachments(args: dict[str, Any]) -> dict[str, Any]:
    account = resolve_account(args.get("account"))
    mailbox = str(args.get("mailbox") or "INBOX")
    uid = str(args.get("uid") or "")
    if not uid:
        raise ToolError("uid is required.")

    output_dir = expand_path(args.get("output_dir")) or expand_path(os.environ.get("CHINA_EMAIL_ATTACHMENT_DIR")) or DEFAULT_ATTACHMENT_DIR
    assert output_dir is not None
    output_dir.mkdir(parents=True, exist_ok=True)

    client = connect_imap(account)
    try:
        select_mailbox(client, mailbox)
        raw = fetch_raw_message(client, uid)
    finally:
        try:
            client.logout()
        except Exception:
            pass

    message = email.message_from_bytes(raw, policy=default)
    saved = []
    for index, part in enumerate(iter_attachment_parts(message), start=1):
        payload = part.get_payload(decode=True) or b""
        filename = sanitize_filename(part.get_filename() or f"attachment-{index}")
        path = output_dir / filename
        if path.exists():
            stem = path.stem
            suffix = path.suffix
            path = output_dir / f"{stem}-{index}{suffix}"
        path.write_bytes(payload)
        saved.append(
            {
                "index": index,
                "filename": filename,
                "content_type": part.get_content_type(),
                "size": len(payload),
                "path": str(path),
            }
        )

    return tool_result({"account": public_account(account), "mailbox": mailbox, "uid": uid, "saved": saved})


def compose_email_message(account: dict[str, Any], args: dict[str, Any], *, draft: bool = False) -> tuple[EmailMessage, dict[str, Any], list[str]]:
    to_recipients = ensure_list(args.get("to"))
    cc_recipients = ensure_list(args.get("cc"))
    bcc_recipients = ensure_list(args.get("bcc"))
    if not to_recipients and not cc_recipients and not bcc_recipients:
        raise ToolError("At least one recipient is required.")

    subject = str(args.get("subject") or "")
    text_body = str(args.get("text") or "")
    html_body = args.get("html")
    if not subject:
        raise ToolError("subject is required.")
    if not text_body and not html_body:
        raise ToolError("text or html body is required.")

    message = EmailMessage()
    from_value = args.get("from") or account["email"]
    if account.get("display_name"):
        from_value = email.utils.formataddr((str(account["display_name"]), str(from_value)))
    message["From"] = str(from_value)
    message["To"] = ", ".join(to_recipients)
    if cc_recipients:
        message["Cc"] = ", ".join(cc_recipients)
    if draft and bcc_recipients:
        message["Bcc"] = ", ".join(bcc_recipients)
    message["Subject"] = subject
    message["Date"] = email.utils.formatdate(localtime=True)
    message["Message-ID"] = email.utils.make_msgid()
    if draft:
        message["X-Unsent"] = "1"

    if html_body:
        message.set_content(text_body or html_to_plain_text(str(html_body)))
        message.add_alternative(str(html_body), subtype="html")
    else:
        message.set_content(text_body)

    attachment_paths = ensure_list(args.get("attachments"))
    attached = []
    for raw_path in attachment_paths:
        path = expand_path(raw_path)
        if not path or not path.exists() or not path.is_file():
            raise ToolError(f"Attachment not found: {raw_path}")
        data = path.read_bytes()
        message.add_attachment(data, maintype="application", subtype="octet-stream", filename=path.name)
        attached.append({"path": str(path), "size": len(data)})

    recipients = to_recipients + cc_recipients + bcc_recipients
    preview = {
        "account": public_account(account),
        "from": str(from_value),
        "to": to_recipients,
        "cc": cc_recipients,
        "bcc_count": len(bcc_recipients),
        "subject": subject,
        "text": text_body,
        "has_html": bool(html_body),
        "attachments": attached,
    }
    return message, preview, recipients


def create_draft(args: dict[str, Any]) -> dict[str, Any]:
    account = resolve_account(args.get("account"))
    message, preview, _ = compose_email_message(account, args, draft=True)
    client = connect_imap(account)
    try:
        draft = append_draft_message(client, account, message, args.get("draft_mailbox"))
    finally:
        try:
            client.logout()
        except Exception:
            pass
    return tool_result({"sent": False, "draft_saved": True, "draft": draft, "preview": preview})


def send_email(args: dict[str, Any]) -> dict[str, Any]:
    account = resolve_account(args.get("account"))
    dry_run = args.get("dry_run", True) is not False
    preview_only = args.get("preview_only", False) is True
    message, preview, recipients = compose_email_message(account, args, draft=dry_run and not preview_only)
    preview["dry_run"] = dry_run

    if dry_run:
        if preview_only:
            return tool_result({"sent": False, "draft_saved": False, "preview": preview})
        client = connect_imap(account)
        try:
            draft = append_draft_message(client, account, message, args.get("draft_mailbox"))
        finally:
            try:
                client.logout()
            except Exception:
                pass
        return tool_result({"sent": False, "draft_saved": True, "draft": draft, "preview": preview})

    client = connect_smtp(account)
    try:
        refused = client.send_message(message, from_addr=account["email"], to_addrs=recipients)
    finally:
        client.quit()
    return tool_result({"sent": True, "refused": refused, "preview": preview})


TOOLS: dict[str, dict[str, Any]] = {
    "china_email_start_setup": {
        "description": "Open a local browser setup wizard so users can configure an email account without editing JSON.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "enum": list(PROVIDER_PRESETS.keys()) + ["custom"],
                    "description": "Optional provider to preselect.",
                },
                "account_name": {"type": "string", "description": "Optional account name to prefill."},
                "open_browser": {"type": "boolean", "default": True},
                "ttl_seconds": {
                    "type": "integer",
                    "minimum": 60,
                    "maximum": 3600,
                    "default": DEFAULT_SETUP_TTL_SECONDS,
                },
            },
            "additionalProperties": False,
        },
        "handler": start_setup_wizard,
    },
    "china_email_list_providers": {
        "description": "List built-in domestic email provider IMAP/SMTP presets.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": list_providers,
    },
    "china_email_list_accounts": {
        "description": "List configured email accounts without exposing secrets.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": list_accounts,
    },
    "china_email_test_connection": {
        "description": "Test IMAP and optionally SMTP login for a configured account.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account": {"type": "string"},
                "check_imap": {"type": "boolean", "default": True},
                "check_smtp": {"type": "boolean", "default": False},
            },
            "additionalProperties": False,
        },
        "handler": test_connection,
    },
    "china_email_search_messages": {
        "description": "Search recent messages in a mailbox and return message summaries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account": {"type": "string"},
                "mailbox": {"type": "string", "default": "INBOX"},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT, "default": 10},
                "scan_limit": {"type": "integer", "minimum": 1, "maximum": MAX_SCAN_LIMIT, "default": DEFAULT_SCAN_LIMIT},
                "query": {
                    "type": "object",
                    "properties": {
                        "from": {"type": "string"},
                        "to": {"type": "string"},
                        "subject": {"type": "string"},
                        "text": {"type": "string"},
                        "since": {"type": "string", "description": "ISO date, for example 2026-04-01"},
                        "before": {"type": "string", "description": "ISO date, for example 2026-05-01"},
                        "unread": {"type": "boolean"},
                        "flagged": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
            },
            "additionalProperties": False,
        },
        "handler": search_messages,
    },
    "china_email_read_message": {
        "description": "Read one message by IMAP UID, including text body and attachment metadata.",
        "inputSchema": {
            "type": "object",
            "required": ["uid"],
            "properties": {
                "account": {"type": "string"},
                "mailbox": {"type": "string", "default": "INBOX"},
                "uid": {"type": "string"},
                "max_body_chars": {"type": "integer", "minimum": 100, "maximum": MAX_BODY_CHARS, "default": DEFAULT_BODY_CHARS},
                "include_html": {"type": "boolean", "default": False},
            },
            "additionalProperties": False,
        },
        "handler": read_message,
    },
    "china_email_save_attachments": {
        "description": "Save all attachments from one message by IMAP UID to a local folder.",
        "inputSchema": {
            "type": "object",
            "required": ["uid"],
            "properties": {
                "account": {"type": "string"},
                "mailbox": {"type": "string", "default": "INBOX"},
                "uid": {"type": "string"},
                "output_dir": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "handler": save_attachments,
    },
    "china_email_create_draft": {
        "description": "Create a message in the configured account's mailbox Drafts folder for user review. Does not send.",
        "inputSchema": {
            "type": "object",
            "required": ["to", "subject"],
            "properties": {
                "account": {"type": "string"},
                "from": {"type": "string"},
                "to": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                "cc": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                "bcc": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                "subject": {"type": "string"},
                "text": {"type": "string"},
                "html": {"type": "string"},
                "attachments": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                "draft_mailbox": {"type": "string", "description": "Optional IMAP mailbox name to save the draft into."},
            },
            "additionalProperties": False,
        },
        "handler": create_draft,
    },
    "china_email_send_email": {
        "description": "Create a mailbox draft by default, or send through SMTP only when dry_run is explicitly false.",
        "inputSchema": {
            "type": "object",
            "required": ["to", "subject"],
            "properties": {
                "account": {"type": "string"},
                "from": {"type": "string"},
                "to": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                "cc": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                "bcc": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                "subject": {"type": "string"},
                "text": {"type": "string"},
                "html": {"type": "string"},
                "attachments": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                "draft_mailbox": {"type": "string", "description": "Optional IMAP mailbox name to save the draft into when dry_run is true."},
                "preview_only": {"type": "boolean", "default": False, "description": "When true with dry_run, return only a chat preview instead of writing a mailbox draft."},
                "dry_run": {"type": "boolean", "default": True, "description": "When true, save a mailbox draft by default. Set false only to actually send."},
            },
            "additionalProperties": False,
        },
        "handler": send_email,
    },
}


def handle_request(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    if request_id is None:
        return None

    try:
        if method == "initialize":
            protocol_version = params.get("protocolVersion") or DEFAULT_PROTOCOL_VERSION
            result = {
                "protocolVersion": protocol_version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            }
            return response(request_id, result)
        if method == "ping":
            return response(request_id, {})
        if method == "tools/list":
            tools = []
            for name, spec in TOOLS.items():
                tools.append(
                    {
                        "name": name,
                        "description": spec["description"],
                        "inputSchema": spec["inputSchema"],
                    }
                )
            return response(request_id, {"tools": tools})
        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments") or {}
            if tool_name not in TOOLS:
                raise ToolError(f"Unknown tool: {tool_name}")
            handler: Callable[[dict[str, Any]], dict[str, Any]] = TOOLS[tool_name]["handler"]
            result = handler(arguments)
            return response(request_id, result)
        return error_response(request_id, -32601, f"Method not found: {method}")
    except ToolError as exc:
        return response(request_id, error_result(str(exc)))
    except Exception as exc:
        eprint(traceback.format_exc())
        return response(request_id, error_result(f"Unexpected {type(exc).__name__}: {exc}"))


def response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def send_message(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def run_stdio_server() -> None:
    eprint("MCP stdio server started")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            send_message(error_response(None, -32700, f"Parse error: {exc}"))
            continue
        result = handle_request(message)
        if result is not None:
            send_message(result)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        run_setup_wizard_cli()
    else:
        run_stdio_server()

"""Fetch recent inbox subjects over IMAP (read-only)."""
import email
import email.policy
import imaplib
import json
import re
import ssl

import keyring

SERVICE = "usagi-mail"
HOSTS = {"naver": "imap.naver.com", "gmail": "imap.gmail.com"}
HEADERS = "BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)]"


def mail_url(name, address, uid, gm_msgid=None):
    if name == "gmail" and gm_msgid:
        return f"https://mail.google.com/mail/?authuser={address}#all/{gm_msgid:x}"
    if name == "naver":
        return f"https://mail.naver.com/v2/read/0/{uid}"  # 0 = inbox; web id == IMAP UID
    return "https://mail.google.com/"


def parse_item(name, address, meta, raw_header):
    uid = int(re.search(rb"UID (\d+)", meta).group(1))
    m = re.search(rb"X-GM-MSGID (\d+)", meta)
    gm = int(m.group(1)) if m else None
    msg = email.message_from_bytes(raw_header, policy=email.policy.default)
    return {
        "account": name,
        "uid": uid,
        "subject": " ".join(str(msg["subject"] or "(제목 없음)").split()),  # unfold
        "sender": str(msg["from"] or ""),
        "date": str(msg["date"] or ""),
        "url": mail_url(name, address, uid, gm),
    }


def fetch(name, address, password, n=10):
    with imaplib.IMAP4_SSL(HOSTS[name], ssl_context=ssl.create_default_context(), timeout=15) as imap:
        imap.login(address, password)
        imap.select("INBOX", readonly=True)  # EXAMINE: never changes read state
        _, data = imap.uid("SEARCH", None, "ALL")
        uids = data[0].split()[-n:]
        if not uids:
            return []
        items = "(UID X-GM-MSGID " + HEADERS + ")" if name == "gmail" else "(UID " + HEADERS + ")"
        _, data = imap.uid("FETCH", b",".join(uids), items)
    out = [parse_item(name, address, d[0], d[1]) for d in data if isinstance(d, tuple)]
    return sorted(out, key=lambda x: x["uid"], reverse=True)


def load_config(path="config.json"):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fetch_all(cfg):
    """Returns {account: list | error string}."""
    result = {}
    for name, address in cfg["accounts"].items():
        try:
            pw = keyring.get_password(SERVICE, address)
            if not pw:
                raise RuntimeError("password not set (run setup_cred.py)")
            result[name] = fetch(name, address, pw, cfg.get("max_items", 10))
        except Exception as e:  # never include password in message
            result[name] = f"{type(e).__name__}: {e}"
    return result


if __name__ == "__main__":
    for name, items in fetch_all(load_config()).items():
        print(f"== {name}")
        if isinstance(items, str):
            print("  ERROR", items)
            continue
        for it in items:
            print(f"  [{it['uid']}] {it['subject']}  ({it['sender']})  {it['url']}")

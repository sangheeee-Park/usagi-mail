from mail import mail_url, parse_item

hdr = b"Subject: =?UTF-8?B?7JWI64WV7ZWY7IS47JqU?=\r\nFrom: =?UTF-8?B?7Jqw7IKs6riw?= <u@x.com>\r\nDate: Mon, 10 Nov 2026 10:00:00 +0900\r\n\r\n"
it = parse_item("gmail", "a@gmail.com", b"1 (X-GM-MSGID 1234567890 UID 42 BODY[...] {99}", hdr)
assert it["subject"] == "안녕하세요", it
assert "우사기" in it["sender"], it
assert it["uid"] == 42
assert it["url"] == "https://mail.google.com/mail/?authuser=a@gmail.com#all/499602d2", it["url"]

it = parse_item("naver", "a@naver.com", b"3 (UID 7 BODY[...] {9}", b"From: a@b.c\r\n\r\n")
assert it["subject"] == "(제목 없음)" and it["url"] == "https://mail.naver.com/v2/read/0/7"
assert mail_url("gmail", "a@gmail.com", 1) == "https://mail.google.com/"

it = parse_item("naver", "a@naver.com", b"3 (UID 8 BODY[...] {9}", b"Subject: =?UTF-8?B?7JWI64WV?=\r\n =?UTF-8?B?7ZWY7IS47JqU?= long\r\n\r\n")
assert "\n" not in it["subject"], it
print("ok unfold")

assert parse_item("naver", "a@naver.com", b"1 (UID 9 BODY[...] {9}", b"\r\n", {9})["unread"] is True
assert parse_item("naver", "a@naver.com", b"1 (UID 9 BODY[...] {9}", b"\r\n", {8})["unread"] is False
print("ok unread")

# ---- usagi state logic
from main import count_new, mood, pick_image

assert mood(2, 5, True) == "new"          # new beats everything
assert mood(0, 5, True) == "error"
assert mood(0, 5, False) == "unread"
assert mood(0, 0, False) == "idle"

assert count_new(None, [{"uid": 9}]) == 0  # first fetch = baseline only
assert count_new(7, [{"uid": 9}, {"uid": 8}, {"uid": 7}]) == 2

files = ["a/idle_1.png", "a/idle_2.png", "a/new_1.png"]
assert pick_image(files, "new") == "a/new_1.png"
assert pick_image(files, "idle", exclude="a/idle_1.png") == "a/idle_2.png"
assert pick_image(files, "error") in files[:2]  # fallback to idle, not new
assert pick_image(["a/new_1.png"], "error") == "a/new_1.png"  # then any
assert pick_image([], "idle") is None
print("ok usagi")

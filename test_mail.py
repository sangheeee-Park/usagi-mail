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
print("ok")

it = parse_item("naver", "a@naver.com", b"3 (UID 8 BODY[...] {9}", b"Subject: =?UTF-8?B?7JWI64WV?=\r\n =?UTF-8?B?7ZWY7IS47JqU?= long\r\n\r\n")
assert "\n" not in it["subject"], it
print("ok unfold")

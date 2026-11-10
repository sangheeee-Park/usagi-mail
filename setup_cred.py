"""Store app passwords in Windows Credential Manager (keyring). Run once."""
import getpass
import json

import keyring

SERVICE = "usagi-mail"

with open("config.json", encoding="utf-8") as f:
    accounts = json.load(f)["accounts"]

for name, address in accounts.items():
    pw = getpass.getpass(f"{name} app password for {address} (Enter to skip): ")
    pw = "".join(pw.split())  # Gmail shows it with spaces
    if pw:
        keyring.set_password(SERVICE, address, pw)
        print(f"  saved {name}")
    else:
        print(f"  skipped {name}")

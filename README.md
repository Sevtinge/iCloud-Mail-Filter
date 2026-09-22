# iCloud Mail Filter

A Dockerized service that periodically scans an iCloud mailbox over IMAP and moves matching messages to a target folder.

## Features

- Scans the source folder on a configurable schedule.
- Matches text in the subject, plain-text body, and HTML body.
- Matches the sender's full `From` header, display name, or email address.
- Supports disabling either filter with `null` or an empty value.
- Moves matched messages using IMAP `COPY`, `STORE`, and `EXPUNGE`.
- Limits the number of messages processed in each run.
- Persists first-run state in `/data/state.json`.
- Fetches message headers before bodies to reduce memory use and avoid loading unnecessary message content.

## Requirements

- Docker Engine with Docker Compose.
- An iCloud email address.
- An Apple app-specific password. Do not use your regular Apple ID password.
- Network access from the container to `imap.mail.me.com:993`.

## Configuration

Copy the example environment file:

```bash
cp .env.example .env
```

Then edit `.env`:

```env
ICLOUD_EMAIL=yourname@icloud.com
ICLOUD_PASSWORD=your-app-specific-password

SOURCE_FOLDER=INBOX
TARGET_FOLDER=Mail/Test

MATCH_TEXT=test
MATCH_FROM=sender@example.com

CHECK_INTERVAL=300
FIRST_RUN_HOURS=24
MAX_PER_RUN=50
IMAP_TIMEOUT=30
```

### Filter behavior

`MATCH_TEXT` is matched case-insensitively against the subject, plain-text body, and converted HTML body.

`MATCH_FROM` is matched case-insensitively against the decoded `From` header, display name, and email address. `MATCH_SENDER` is also supported as an alias, but `MATCH_FROM` takes precedence when both are set.

Both filters use substring matching. When both filters are enabled, a message must satisfy both conditions before it is moved.

Set either filter to `null` or leave it empty to disable that filter:

```env
MATCH_TEXT=null
MATCH_FROM=null
```

If both filters are disabled, every candidate message may be moved. Use this configuration with care.

## iCloud IMAP mailbox names

Apple's iCloud Mail interface has seven default mail folders: Inbox, VIP, Drafts, Sent, Archive, Trash, and Junk. The names shown by the web interface are not always the same as the mailbox names exposed through IMAP.

For an English-language iCloud account, the commonly used IMAP mailbox names are:

| iCloud Mail folder | Typical IMAP mailbox name | Notes |
| --- | --- | --- |
| Inbox | `INBOX` | The standard IMAP inbox name. |
| Drafts | `Drafts` | Unsent drafts. |
| Sent | `Sent Messages` | iCloud commonly uses `Sent Messages`, not `Sent` or `Sent Items`. |
| Trash / Bin | `Deleted Messages` | iCloud commonly uses `Deleted Messages`, not `Trash` or `Deleted Items`. |
| Junk | `Junk` | Do not use `Spam` or `Junk E-mail` unless your account actually lists that name. |
| Archive | `Archive` | Archived messages. |
| VIP | Account-dependent | VIP may be represented as a category or special view instead of a normal IMAP mailbox. |
| Notes | Account-dependent | Some accounts expose an additional `Notes` mailbox. |

These names are only defaults. Folder names can differ because of account language, mailbox behavior settings, client-created folders, or previously created custom folders. Always use the names returned by the account's IMAP `LIST` command instead of assuming that a web UI label is the IMAP mailbox name.

To list the exact mailbox names for the account, run this read-only check from a machine with Python and set the credentials as environment variables first:

```bash
ICLOUD_EMAIL='yourname@icloud.com' ICLOUD_PASSWORD='your-app-specific-password' \
python - <<'PY'
import imaplib
import os

imap = imaplib.IMAP4_SSL("imap.mail.me.com", 993)
imap.login(os.environ["ICLOUD_EMAIL"], os.environ["ICLOUD_PASSWORD"])
status, mailboxes = imap.list('""', "*")
if status != "OK":
    raise SystemExit(f"LIST failed: {status}")
for mailbox in mailboxes:
    if mailbox:
        print(mailbox.decode("utf-8", errors="replace"))
imap.logout()
PY
```

Use the exact mailbox name returned by this command in `SOURCE_FOLDER` or `TARGET_FOLDER`. For example:

```env
SOURCE_FOLDER=INBOX
TARGET_FOLDER=Deleted Messages
```

A folder such as `Mail/Junk` is a custom folder hierarchy, not one of the standard names above, unless it appears in the output of `LIST` for your account.

## Running the service

Build and start the container:

```bash
docker compose up -d --build
```

Follow the logs:

```bash
docker compose logs -f
```

Stop the service:

```bash
docker compose down
```

## Scan behavior

- On the first run, only messages received within the last `FIRST_RUN_HOURS` hours are considered.
- After the first run, only unread messages are considered.
- At most `MAX_PER_RUN` candidate messages are processed per run.
- Matched messages are copied to `TARGET_FOLDER`, marked as deleted in the source folder, and expunged.
- The target folder is created automatically when possible.
- Delete `data/state.json` or the entire `data/` directory to make the next run behave as a first run.

## Project files

- `filter.py` - IMAP polling and filtering logic.
- `compose.yml` - Docker Compose service definition.
- `Dockerfile` - Container image definition.
- `.env.example` - Example configuration.
- `data/state.json` - Runtime state persisted through the bind mount.

## Security notes

- `.env` contains mailbox credentials and is excluded by `.gitignore`. Never commit it to source control.
- Use an Apple app-specific password instead of your primary Apple ID password.
- If the app-specific password has been exposed, revoke it in your Apple account and create a new one.

## License

This project is licensed under the [MIT License](LICENSE).

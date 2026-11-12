# Vandus Dice Bot

A Discord bot implementing a Success Point (SP) dice system for a tabletop-style
RP server, backed by a Google Sheet as the character database, plus a tkinter
desktop app to start/stop the bot without a terminal.

## Project layout

```
bot/                Bot core: dice math, sheets access, slash commands
  dice.py            NdM rolling (d4-d20) + SP counting
  models.py           Character / WeaponOption dataclasses, strict cell parsing
  sheets.py            Google Sheets access layer (gspread), re-fetched every call
  commands.py           /roll and /attack slash commands, error handling
  errors.py             Coded error types (E101...) with Thai player messages
  reporting.py          Player error replies, controller log entries, redaction
  weapon_cache.py       60 s in-memory weapon list for autocomplete
  main.py                Bot entrypoint (build_bot / standalone `python -m bot.main`)
gui/                tkinter desktop controller
  config_store.py       Settings file in %LOCALAPPDATA% (+ migration from older builds)
  bot_runner.py           Background thread + asyncio loop + auto-shutdown timer, log forwarding
  controller.py            The tkinter window itself, including the Log box
controller_app.py    Entry point used for the PyInstaller build
tests/              pytest tests (dice, sheets, commands, error reporting, Log box)
build/controller.spec  PyInstaller spec for the .exe build
.env.example        Template for standalone (non-GUI) bot runs
```

Requires Python 3.10 or newer (developed and tested on 3.14) for running from source;
the built .exe needs no Python.

## 1. Get a Discord bot token

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and click **New Application**.
2. Under **Bot**, click **Add Bot**, then **Reset Token** to reveal/copy the token. Keep this secret.
3. Under **Bot**, enable any intents you need (this bot only uses default intents — no privileged intents required).

## 2. Invite the bot to your server

1. In the Developer Portal, go to **OAuth2 -> URL Generator**.
2. Scopes: check `bot` and `applications.commands`.
3. Bot permissions: `Send Messages`, `Use Slash Commands` (Read Message History is helpful but not required).
4. Open the generated URL and select your server to invite the bot.

## 3. Set up the Google Sheet + service account

1. Create a Google Cloud project, enable the **Google Sheets API** and **Google Drive API**.
2. Create a **Service Account**, then create a JSON key for it and download it.
3. Share your character-database Google Sheet with the service account's email address (found inside the JSON, `client_email`), giving it at least **Viewer** access.
4. The sheet must have three tabs named exactly `Final Sum`, `Player Skill`, `Weapon Info`.
   The first row of each tab is its header row:
   - `Final Sum`: `Discord ID` (the player's Discord username), `ID`, `Name`, optionally
     `Race`, and one column per stat: `STR`, `CON`, `DEX`, `INT`, `WIS`.
   - `Player Skill`: `ID` (matching `Final Sum`) and one column per skill (a `Name`
     column is fine; the bot doesn't read it).
   - `Weapon Info`: `Code`, `Weapon Name`, `Skill`, `Attribute`. A weapon with two modes
     (e.g. melee and thrown) puts one skill per line in `Skill` and the matching
     attributes, one per line, in `Attribute`; a skill containing "Thrown" is listed
     as "<name> (ขว้าง)".

   A missing tab or column is reported as E303 / E304 (see the error codes below).

### Where to drop the service account JSON

- **Standalone / dev mode:** place the file anywhere and point `GOOGLE_SERVICE_ACCOUNT_JSON` in your `.env` at it (see `.env.example`).
- **GUI controller:** use the "เลือกไฟล์..." (Choose file) button to browse to the JSON file. Its path is saved locally in `gui_config.json` in your per-user app data directory (see below) — the file itself is never copied or embedded, only its path is remembered.

Never commit the JSON key file. `.gitignore` already excludes `*.json` (other than files ending in `.example.json`).

## Running standalone (no GUI, for development)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt

copy .env.example .env
# edit .env: DISCORD_BOT_TOKEN, GOOGLE_SERVICE_ACCOUNT_JSON, GOOGLE_SHEET_NAME

python -m bot.main
```

## Running the GUI controller from source

From the project root, with the venv active:

```bash
python -m gui.controller
```

The `-m` matters: `python gui\controller.py` fails with
`ModuleNotFoundError: No module named 'gui'`, because running a file directly puts
`gui\` rather than the project root on Python's import path. `python controller_app.py`
(the same entry point the .exe uses) also works from the project root.

Fill in the token, JSON path, and sheet name once (see "Where the settings are stored"
below). Pick an auto-shutdown mode if you want the bot to stop itself after a session,
then click **Start**. The status indicator reflects the real Discord connection state,
not just the button click. On connect the Log box also reports whether the Google
Sheet could be read, with the service account's email address.

## Where the settings are stored

The controller saves the token, the JSON path, the sheet name and the auto-shutdown
choice to:

- `%LOCALAPPDATA%\DiceBotController\gui_config.json` on Windows
- `~/.dicebotcontroller/gui_config.json` where `LOCALAPPDATA` isn't set

The folder name is fixed in `gui/config_store.py`; it does not depend on the .exe's
name or location, so renaming, moving, rebuilding or replacing the .exe keeps the
settings. (Changing that folder name in the code would make every user start from an
empty config.)

Older builds kept `gui_config.json` next to the .exe (or in the project root when run
from source). If no config exists at the new location yet, the first start copies
that old file over automatically; the old file is left where it was.

The token is stored in plain text, readable by anyone who can open your Windows user
profile.

## Building the standalone .exe with PyInstaller

From the project root, with the venv active and `pyinstaller` installed
(`pip install -r requirements-dev.txt` includes it):

```bash
pyinstaller build/controller.spec
```

For a clean rebuild (drops PyInstaller's cache and overwrites the old .exe without
asking), use `pyinstaller --clean --noconfirm build/controller.spec`.

No `--distpath` flag is needed — the spec sets the output location itself: it
lands in a sibling folder next to the project root, named
`DiceBotController-Release`. For example, if this project lives at
`C:\Work\Commu\Vandus\DiscordBot`, the exe is written to
`C:\Work\Commu\Vandus\DiceBotController-Release\DiceBotController.exe` — kept
outside the project directory so it's easy to hand off without dragging
project files along. The intermediate build cache still lands in
`build/controller/` inside the project, same as PyInstaller's default.

The output executable is `DiceBotController.exe` in that `DiceBotController-Release`
folder (the name comes from `name=` in the spec). Copy it anywhere on the target Windows
PC — no Python installation required there. Its settings live in `%LOCALAPPDATA%`, not
next to the .exe (see "Where the settings are stored").

## Running tests

```bash
pip install -r requirements-dev.txt
pytest
```

The Log box tests need Tk; without a display they are skipped.

## Dice system reference

### Commands

- `/roll type:<Normal|ADV|DIS>` with at most one of:
  - nothing: rolls 6d6, no character needed;
  - `attribute:<STR|CON|DEX|INT|WIS>`: rolls as many d6 as the character's stat in
    `Final Sum`;
  - `dice:<NdM>`: rolls N dice with M faces, e.g. `3d6`, `2d8`, `4d20`. N is 1-100,
    M is one of 4, 6, 8, 10, 12, 20. Case and spaces don't matter (`3D6`, `3 d 6`).

  Giving both `attribute` and `dice` is an error (E101).
- `/attack weapon:<name> type:<Normal|ADV|DIS>` rolls (weapon skill from `Player Skill`)
  + (weapon attribute from `Final Sum`) d6. A blank skill cell counts as 0. A pool
  above 100 dice is refused (E206).

### Pass values

Success points (SP) count the dice that land in the pass range, from `min_pass` up to
the highest face:

```
min_pass = faces - round(faces * ratio) + 1
ratio:  Normal 1/2   ADV 2/3   DIS 1/3
```

This reproduces the original d6 ranges and gives:

| Die | Normal | ADV | DIS |
|---|---|---|---|
| d4  | 3-4 (50%)   | 2-4 (75%)  | 4 (25%)     |
| d6  | 4-6 (50%)   | 3-6 (67%)  | 5-6 (33%)   |
| d8  | 5-8 (50%)   | 4-8 (62%)  | 6-8 (38%)   |
| d10 | 6-10 (50%)  | 4-10 (70%) | 8-10 (30%)  |
| d12 | 7-12 (50%)  | 5-12 (67%) | 9-12 (33%)  |
| d20 | 11-20 (50%) | 8-20 (65%) | 14-20 (35%) |

Normal is exactly 50% on every die; ADV and DIS land near 2/3 and 1/3 but not exactly,
because the threshold is rounded to a whole face.

### Output format

```
rolled [ADV] 2d8: 5, 3
SP: 1
```

```
Aria Silverleaf use Knife
Knife Fighting 2 + STR 4 = 6d6
rolled [Normal] 6d6: 3, 4, 4, 1, 6, 5
SP: 4
```

## Log box and error codes

The controller's Log box shows one line per successful command, e.g.
`[21:05:33] /attack haconn -> Play C, ดาบใหญ่, 5d6 ADV, SP 4`, and one entry per
error. It keeps the newest 500 lines.

Every error has a stable code. The player gets an ephemeral Thai message with the
code (e.g. `❌ [E203] ...`); the Log box gets the same code with the technical
detail: who ran which command, the character, weapon, skill and attribute, the raw
cell value where one is involved, the exception and where it was raised. Unexpected
errors (E900) get a full traceback in the log and a generic message for the player.

| Code | Meaning | Usually fixed by |
|---|---|---|
| E101 | `dice` and `attribute` given together | player |
| E102 | dice notation is not NdM | player |
| E103 | unsupported die size (not d4/d6/d8/d10/d12/d20) | player |
| E104 | dice count in the notation outside 1-100 | player |
| E105 | weapon name not in the weapon list | player (pick from autocomplete) |
| E201 | no row in `Final Sum` whose `Discord ID` is the player's username | GM |
| E202 | character's ID has no row in `Player Skill` | GM |
| E203 | stat cell is blank, text or a decimal (raw value in the log) | GM |
| E204 | skill cell is text or a decimal (a blank skill cell counts as 0) | GM |
| E205 | computed dice count is 0 or negative | GM |
| E206 | computed dice count is above 100 | GM |
| E301 | weapon's Skill is not a column in `Player Skill` | GM |
| E302 | weapon's Attribute is not STR/CON/DEX/INT/WIS | GM |
| E303 | a required tab is missing or renamed | GM |
| E304 | a required column is missing from a tab's header row | GM |
| E401 | service account JSON missing, corrupt or rejected by Google | GM (Controller) |
| E403 | sheet not shared with the service account (`client_email` is in the log) | GM |
| E404 | spreadsheet name/key/URL not found (or not shared, when opened by name) | GM (Controller) |
| E408 | Google Sheets did not answer in time | retry |
| E429 | Google Sheets read quota used up for the moment | wait ~1 min |
| E450 | could not reach Google (network) | retry / check internet |
| E499 | other Google Sheets API error | retry |
| E900 | unexpected error in the bot (full traceback in the log) | developer |
| E901 | the bot could not send its reply to Discord (log only) | developer |

The log never shows the bot token or the service account key; for the key file it
shows only the file path and `client_email`.

## Security notes

- No credentials are committed anywhere in this repo. `.env.example` and the PyInstaller
  spec contain placeholders only.
- `.gitignore` excludes `.env` and `.env.*` (except `.env.example`), all `*.json` files
  (service account keys), `gui_config.json`, key files (`*.pem`, `*.key`, `*.p12`,
  `*.pfx`) and IDE folders (`.idea/`, `.vscode/`).
- The Log box shows technical error detail, but every entry and every Discord reply goes
  through a redaction step first: the bot token, private keys and Google OAuth tokens
  are replaced with `[REDACTED]`. For the key file only its path and `client_email` are
  ever shown.
- `tests/` contains deliberately fake values shaped like a private key and a Discord
  token, used to test that redaction. They are not credentials.

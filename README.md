# Vandus Dice Bot

A Discord bot implementing a Success Point (SP) dice system for a tabletop-style
RP server, backed by a Google Sheet as the character database, plus a tkinter
desktop app to start/stop the bot without a terminal.

## Project layout

```
bot/                Bot core: dice math, sheets access, slash commands
  dice.py            Nd6 rolling + SP counting
  models.py           Character / WeaponOption dataclasses
  sheets.py            Google Sheets access layer (gspread), re-fetched every call
  commands.py           /roll and /attack slash commands
  errors.py             User-facing (Thai) error types
  main.py                Bot entrypoint (build_bot / standalone `python -m bot.main`)
gui/                tkinter desktop controller
  config_store.py       Local JSON persistence for token/paths/settings
  bot_runner.py           Background thread + asyncio loop + auto-shutdown timer
  controller.py            The tkinter window itself
controller_app.py    Entry point used for the PyInstaller build
tests/              pytest unit tests (dice math, sheet parsing, command logic)
build/controller.spec  PyInstaller spec for the .exe build
.env.example        Template for standalone (non-GUI) bot runs
```

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
4. The sheet must have three tabs named exactly `Final Sum`, `Player Skill`, `Weapon Info` with the columns described in the bot's design notes.

### Where to drop the service account JSON

- **Standalone / dev mode:** place the file anywhere and point `GOOGLE_SERVICE_ACCOUNT_JSON` in your `.env` at it (see `.env.example`).
- **GUI controller:** use the "เลือกไฟล์..." (Choose file) button to browse to the JSON file. Its path is saved locally in `gui_config.json` next to the app — the file itself is never copied or embedded, only its path is remembered.

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

```bash
python gui\controller.py
```

Fill in the token, JSON path, and sheet name once — they're saved to `gui_config.json`
next to the app (also gitignored) so you only enter them once. Pick an auto-shutdown
mode if you want the bot to stop itself after a session, then click **Start**. The
status indicator reflects the real Discord connection state, not just the button click.

## Building the standalone .exe with PyInstaller

From the project root, with the venv active and `pyinstaller` installed
(`pip install -r requirements-dev.txt` includes it):

```bash
pyinstaller build/controller.spec
```

No `--distpath` flag is needed — the spec sets the output location itself: it
lands in a sibling folder next to the project root, named
`DiceBotController-Release`. For example, if this project lives at
`C:\Work\Commu\Vandus\DiscordBot`, the exe is written to
`C:\Work\Commu\Vandus\DiceBotController-Release\DiceBotController.exe` — kept
outside the project directory so it's easy to hand off without dragging
project files along. The intermediate build cache still lands in
`build/controller/` inside the project, same as PyInstaller's default.

The output executable is `DiceBotController.exe` in that `DiceBotController-Release`
folder. Copy it anywhere on the target Windows PC — no Python installation required
there. On first run it will create
`gui_config.json` next to itself to remember the token/paths/settings entered in the GUI.

## Running tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Dice system reference

Every roll is Nd6; success points (SP) count dice landing in the pass range:

| Roll type | Pass values |
|---|---|
| Normal | 4, 5, 6 |
| ADV    | 3, 4, 5, 6 |
| DIS    | 5, 6 |

Output format:
```
rolled [Normal] 6d6: 3, 4, 4, 1, 6, 5
SP: 4
```

## Security notes

- No credentials are committed anywhere in this repo. `.env.example` and the PyInstaller
  spec contain placeholders only.
- `.gitignore` excludes the real `.env`, all `*.json` service account key files, and
  `gui_config.json` (the GUI's local credential store).
- The GUI never prints the raw token or JSON key contents to its log box or stdout —
  only connection status lines (e.g. "เชื่อมต่อ Discord สำเร็จ").

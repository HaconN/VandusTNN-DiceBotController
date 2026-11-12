import json
from pathlib import Path

from gui.config_store import DEFAULT_CONFIG, ConfigStore, _app_data_dir


def make_store(tmp_path, monkeypatch, new_dir_name="new", legacy_dir_name="legacy"):
    store = ConfigStore()
    store.path = tmp_path / new_dir_name / "gui_config.json"
    store.legacy_path = tmp_path / legacy_dir_name / "gui_config.json"
    return store


def test_load_returns_defaults_when_nothing_exists(tmp_path):
    store = make_store(tmp_path, None)
    assert store.load() == DEFAULT_CONFIG


def test_save_then_load_roundtrips(tmp_path):
    store = make_store(tmp_path, None)
    config = dict(DEFAULT_CONFIG)
    config["discord_bot_token"] = "secret-token"

    store.save(config)

    assert store.path.exists()
    assert store.load()["discord_bot_token"] == "secret-token"


def test_save_creates_parent_directory(tmp_path):
    store = make_store(tmp_path, None)
    assert not store.path.parent.exists()

    store.save(dict(DEFAULT_CONFIG))

    assert store.path.exists()


def test_load_migrates_legacy_config_when_new_path_missing(tmp_path):
    store = make_store(tmp_path, None)
    store.legacy_path.parent.mkdir(parents=True)
    legacy_config = dict(DEFAULT_CONFIG)
    legacy_config["discord_bot_token"] = "legacy-secret"
    legacy_config["sheet_name"] = "MySheet"
    with open(store.legacy_path, "w", encoding="utf-8") as f:
        json.dump(legacy_config, f)

    loaded = store.load()

    assert loaded["discord_bot_token"] == "legacy-secret"
    assert loaded["sheet_name"] == "MySheet"
    # Migration writes it forward to the new location.
    assert store.path.exists()
    with open(store.path, "r", encoding="utf-8") as f:
        assert json.load(f)["discord_bot_token"] == "legacy-secret"


def test_load_prefers_new_config_over_legacy(tmp_path):
    store = make_store(tmp_path, None)
    store.legacy_path.parent.mkdir(parents=True)
    with open(store.legacy_path, "w", encoding="utf-8") as f:
        json.dump({**DEFAULT_CONFIG, "discord_bot_token": "legacy-secret"}, f)
    store.save({**DEFAULT_CONFIG, "discord_bot_token": "new-secret"})

    loaded = store.load()

    assert loaded["discord_bot_token"] == "new-secret"


def test_load_ignores_missing_legacy_config(tmp_path):
    store = make_store(tmp_path, None)
    assert not store.legacy_path.exists()

    assert store.load() == DEFAULT_CONFIG


def test_load_ignores_corrupt_legacy_config(tmp_path):
    store = make_store(tmp_path, None)
    store.legacy_path.parent.mkdir(parents=True)
    store.legacy_path.write_text("not json", encoding="utf-8")

    assert store.load() == DEFAULT_CONFIG
    assert not store.path.exists()


def test_app_data_dir_uses_localappdata_when_set(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert _app_data_dir() == tmp_path / "DiceBotController"


def test_app_data_dir_falls_back_to_home_when_localappdata_unset(monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    assert _app_data_dir() == Path.home() / ".dicebotcontroller"

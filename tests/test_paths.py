"""경로 기본값과 환경변수 오버라이드."""

import importlib

import platformdirs

from backend.core import paths


def _reload(monkeypatch, **env):
    for name in ("KISEVENT_APP_DIR", "KISEVENT_LOG_DIR", "KISEVENT_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return importlib.reload(paths)


def test_env_overrides(tmp_path, monkeypatch):
    module = _reload(
        monkeypatch,
        KISEVENT_APP_DIR=str(tmp_path / "app"),
        KISEVENT_LOG_DIR=str(tmp_path / "logs"),
        KISEVENT_DATA_DIR=str(tmp_path / "data"),
    )
    try:
        assert module.APP_DIR == tmp_path / "app"
        assert module.LOG_DIR == tmp_path / "logs"
        assert module.DATA_DIR == tmp_path / "data"
        assert module.DB_PATH == tmp_path / "data" / "events.db"
        assert module.IMAGE_DIR == tmp_path / "data" / "images"
    finally:
        _reload(monkeypatch)


def test_log_dir_defaults_under_app_dir(tmp_path, monkeypatch):
    module = _reload(monkeypatch, KISEVENT_APP_DIR=str(tmp_path / "app"))
    try:
        assert module.LOG_DIR == tmp_path / "app" / "logs"
    finally:
        _reload(monkeypatch)


def test_windows_app_dir_uses_localappdata(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    # platformdirs는 import 시점의 sys.platform으로 구현을 고르므로 함께 reload한다.
    # 실제 Windows API는 macOS에서 부를 수 없으니 환경변수 해석기로 돌린다.
    importlib.reload(platformdirs)
    monkeypatch.setattr(
        platformdirs.windows, "_resolve_win_folder", platformdirs.windows.get_win_folder_from_env_vars
    )
    module = _reload(monkeypatch)
    try:
        assert module.APP_DIR == tmp_path / "Local" / "kisevent"
        assert module.LOG_DIR == tmp_path / "Local" / "kisevent" / "logs"
    finally:
        monkeypatch.undo()
        importlib.reload(platformdirs)
        _reload(monkeypatch)

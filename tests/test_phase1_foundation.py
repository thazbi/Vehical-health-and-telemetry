from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_core_files_exist() -> None:
    assert (REPO_ROOT / ".gitignore").exists()
    assert (REPO_ROOT / ".env.example").exists()
    assert (REPO_ROOT / "pyproject.toml").exists()
    assert (REPO_ROOT / "README.md").exists()
    assert (REPO_ROOT / "requirements-dev.txt").exists()
    assert (REPO_ROOT / "Makefile").exists()


def test_service_folders_exist() -> None:
    assert (REPO_ROOT / "services").is_dir()
    assert (REPO_ROOT / "services" / "vehicle_service").is_dir()
    assert (REPO_ROOT / "services" / "telemetry_service").is_dir()
    assert (REPO_ROOT / "services" / "alert_service").is_dir()


def test_example_env_contains_required_variables() -> None:
    env_text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    required = [
        "LOG_LEVEL",
        "FAILURE_SIMULATION_ENABLED",
        "VEHICLE_SERVICE_URL",
        "TELEMETRY_SERVICE_URL",
        "ALERT_SERVICE_URL",
        "BATTERY_TEMPERATURE_THRESHOLD",
    ]

    for variable in required:
        assert variable in env_text

import pytest

from mosign import tracker


def test_find_model_prefers_existing_file(isolated_home):
    assert tracker.find_model() is None or tracker.find_model().is_file()
    dest = isolated_home / "models" / tracker.MODEL_NAME
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"fake")
    found = tracker.find_model()
    assert found is not None and found.is_file()


def test_download_failure_gives_clear_error(isolated_home):
    with pytest.raises(tracker.ModelNotFoundError) as err:
        tracker.download_model(url="http://127.0.0.1:9/nothing-here")
    assert "hand model" in str(err.value)
    assert not (isolated_home / "models" / "hand_landmarker.part").exists()


def test_to_gesture_space_scales_x_by_aspect():
    assert tracker.to_gesture_space([(0.5, 0.5)], 1280, 720) == [(0.5 * 1280 / 720, 0.5)]


def test_skeleton_has_21_points():
    used = {i for pair in tracker.HAND_CONNECTIONS for i in pair}
    assert used == set(range(21))


def test_tasks_backend_reports_missing_model(tmp_path):
    pytest.importorskip("mediapipe")
    with pytest.raises(tracker.ModelNotFoundError):
        tracker.HandTracker(backend="tasks", model_path=tmp_path / "missing.task")


def test_tasks_backend_rejects_bad_model_file(tmp_path):
    """A corrupt model must fail loudly at startup, not silently mid-run."""
    pytest.importorskip("mediapipe")
    bad = tmp_path / "bad.task"
    bad.write_bytes(b"not a model")
    with pytest.raises(Exception):
        tracker.HandTracker(backend="tasks", model_path=bad)

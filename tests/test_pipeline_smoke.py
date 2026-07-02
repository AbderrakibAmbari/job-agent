"""Smoke test: the public surface of run_pipeline / main is intact.

This test does NOT call run_pipeline() — that hits the network. It only
verifies the import wiring main.py depends on after plan 005.
"""
import inspect
import sys


def test_run_pipeline_is_importable_and_has_min_score_kwarg():
    from nodes.pipeline import run_pipeline
    sig = inspect.signature(run_pipeline)
    assert "min_score" in sig.parameters
    assert sig.parameters["min_score"].default == 70


def test_main_module_imports_without_running_pipeline():
    # Importing main.py runs the tee-log setup but must NOT invoke
    # run_pipeline (that's guarded by `if __name__ == "__main__"`).
    # Wrap the import to restore stdout/stderr since main.py replaces
    # them with a Tee at module scope.
    saved_stdout, saved_stderr = sys.stdout, sys.stderr
    try:
        import main  # noqa: F401
    finally:
        sys.stdout, sys.stderr = saved_stdout, saved_stderr
    # No assertion needed — a clean import is the test.

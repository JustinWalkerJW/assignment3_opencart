"""Independent setup, teardown and assignment Pass/Fail/Error evidence reporting."""

import csv
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import selenium
from selenium import webdriver
from selenium.webdriver.chrome.service import Service

from cart_tests.evidence import Evidence, utc_now
from cart_tests.shop import SetupIssue, Shop


def pytest_addoption(parser):
    group = parser.getgroup("hanlin-cart")
    group.addoption("--headless", action="store_true", help="Run Chrome without a window")
    group.addoption("--wait-seconds", type=float, default=20, help="Explicit UI wait timeout")
    group.addoption("--artifacts-dir", default="artifacts", help="Parent of unique run folders")
    group.addoption("--driver-path", default=None, help="Optional local chromedriver executable")
    group.addoption("--chrome-binary", default=None, help="Optional Chrome executable")
    group.addoption("--driver-debug", action="store_true", help="Save verbose ChromeDriver startup logs")


def pytest_configure(config):
    if config.getoption("wait_seconds") <= 0:
        raise pytest.UsageError("--wait-seconds must be positive")
    # Parallel execution needs a separate reporting design; this assignment is serial.
    if getattr(config.option, "numprocesses", None):
        raise pytest.UsageError("Run these nine scenarios serially; remove the -n option")
    config.hanlin_results = {}
    config.hanlin_run_dir = None


def pytest_collection_modifyitems(config, items):
    if config.getoption("collectonly"):
        return  # Collection must not create results or launch a browser.
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:6]
    config.hanlin_run_dir = Path(config.getoption("artifacts_dir")).resolve() / run_id
    config.hanlin_run_dir.mkdir(parents=True)
    seen = set()
    for item in items:
        marker = item.get_closest_marker("scenario")
        if marker is None:
            raise pytest.UsageError(f"Missing scenario marker: {item.nodeid}")
        sid = marker.kwargs["id"]
        if sid in seen:
            raise pytest.UsageError(f"Duplicate scenario ID: {sid}")
        seen.add(sid)
        item.hanlin_spec = marker.kwargs
        item.hanlin_evidence = Evidence(config.hanlin_run_dir / sid, sid)
        config.hanlin_results[sid] = {
            "test_case": sid.split("-")[0], "function": marker.kwargs["function"],
            "tester": "Hanlin Yu", "nodeid": item.nodeid, "status": "Not run",
            "phases": {}, "duration_seconds": 0,
        }


@pytest.fixture
def evidence(request):
    return request.node.hanlin_evidence


@pytest.fixture
def shop(request, evidence):
    """One new temporary Chrome profile per scenario; no user's existing session."""
    options = webdriver.ChromeOptions()
    options.add_argument("--window-size=1440,1100")
    options.add_argument("--lang=en-US")
    if request.config.getoption("headless"):
        options.add_argument("--headless=new")
    binary = request.config.getoption("chrome_binary")
    if binary:
        options.binary_location = str(Path(binary).expanduser().resolve())
    driver_path = request.config.getoption("driver_path")
    evidence.environment = {
        "python": platform.python_version(), "platform": platform.platform(),
        "selenium": selenium.__version__, "pytest": pytest.__version__,
        "headless": request.config.getoption("headless"),
        "started_utc": utc_now(), "browser_session_created": False,
    }
    evidence.record("browser_start_requested", browser="Chrome")
    service = Service(
        executable_path=driver_path,
        log_output=str(evidence.folder / "chromedriver.log"),
        service_args=["--verbose"] if request.config.getoption("driver_debug") else [],
    )
    driver = webdriver.Chrome(options=options, service=service)
    evidence.driver = driver
    app = Shop(driver, request.config.getoption("wait_seconds"))

    # Register before preparing data so cleanup also occurs on a setup error.
    def close_session():
        try:
            app.cleanup()
        except Exception as exc:
            evidence.warnings.append(f"UI cleanup incomplete: {type(exc).__name__}: {exc}")
        finally:
            try:
                driver.quit()
            except Exception as exc:
                evidence.warnings.append(f"Chrome close error: {type(exc).__name__}: {exc}")
    request.addfinalizer(close_session)
    driver.implicitly_wait(0)  # Do not mix implicit and explicit waits.
    driver.set_page_load_timeout(45)
    caps = driver.capabilities
    evidence.environment.update({
        "browser": caps.get("browserName"), "browser_version": caps.get("browserVersion"),
        "chromedriver": caps.get("chrome", {}).get("chromedriverVersion"),
        "browser_session_created": True, "window": driver.get_window_size(),
    })
    spec = request.node.hanlin_spec
    try:
        app.open_cart()
        app.set_us_dollars()
        app.expect_cart({})
        for pid, qty in spec["cart"].items():
            app.check_product(pid, minimum_qty=max(qty, spec.get("required_stock", {}).get(pid, 1)))
            app.add_product(pid, qty)
        if spec.get("product") is not None:
            pid = spec["product"]
            app.check_product(pid, minimum_qty=spec.get("required_stock", {}).get(pid, 1))
        app.open_cart()
        baseline = app.expect_cart(spec["cart"])
        evidence.record("setup_complete", baseline=repr(baseline))
    except AssertionError as exc:
        raise SetupIssue(f"Cannot establish this scenario's baseline: {exc}") from exc
    return app


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    evidence = getattr(item, "hanlin_evidence", None)
    if evidence is None:
        return
    result = item.config.hanlin_results[evidence.scenario_id]
    phase_status = report.outcome
    if report.failed:
        # pytest groups call-phase exceptions as failed. The assignment distinguishes
        # an assertion mismatch (Fail) from an execution/setup exception (Error).
        assertion = call.excinfo is not None and call.excinfo.errisinstance(AssertionError)
        status = "Fail" if report.when == "call" and assertion else "Error"
        if result["status"] != "Error":
            result["status"] = status
        phase_status = status
        result.setdefault("problems", []).append(str(report.longrepr))
        try:
            evidence.capture(f"{report.when}_{status.lower()}")
        except Exception as exc:
            evidence.warnings.append(f"Failure screenshot unavailable: {type(exc).__name__}: {exc}")
    elif report.skipped:
        if result["status"] == "Not run":
            result["status"] = "Skipped"
    elif report.when == "call" and result["status"] == "Not run":
        result["status"] = "Pass"
    result["phases"][report.when] = phase_status
    result["duration_seconds"] += report.duration
    evidence.write(result)


def pytest_sessionfinish(session, exitstatus):
    config = session.config
    folder = config.hanlin_run_dir
    if folder is None:
        return
    records = []
    for sid, result in config.hanlin_results.items():
        records.append({"scenario_id": sid, **result,
                        "evidence_folder": sid, "duration_seconds": round(result["duration_seconds"], 3)})
    summary = {"completed_utc": utc_now(), "pytest_exit_code": int(exitstatus), "results": records}
    (folder / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    fields = ["scenario_id", "test_case", "function", "tester", "status", "duration_seconds", "evidence_folder"]
    with (folder / "summary.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if config.hanlin_run_dir is not None:
        terminalreporter.write_sep("=", f"Assignment evidence: {config.hanlin_run_dir}")

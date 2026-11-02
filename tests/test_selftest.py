from linkdn_connect import selftest


def test_self_test_passes_and_writes_the_report(tmp_path):
    report = tmp_path / "report.txt"
    assert selftest.run(report) == 0
    text = report.read_text()
    assert "templates: ok" in text
    assert "vision: ok" in text
    assert text.rstrip().endswith("RESULT: PASS")

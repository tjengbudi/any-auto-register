from __future__ import annotations

from tools.i18n_lint import find_unbaselined, load_baseline, scan


def test_no_unbaselined_han_bearing_log_call_sites():
    scanned = scan()
    baseline = load_baseline()
    unbaselined = find_unbaselined(scanned, baseline)
    assert unbaselined == []


def test_scan_detects_a_new_han_bearing_log_call_site(tmp_path):
    # A synthetic tree under one of the six fixed scan roots, exercising the
    # detector itself rather than the real repo's already-clean state.
    core_dir = tmp_path / "core"
    core_dir.mkdir()
    (core_dir / "example.py").write_text(
        'class X:\n'
        '    def run(self):\n'
        '        self.log("新错误")\n'
        '        self.log(f"失败: {1}")\n',
        encoding="utf-8",
    )

    scanned = scan(tmp_path)

    assert "core/example.py" in scanned
    sites = scanned["core/example.py"]
    assert len(sites) == 2
    texts = {text for _, text, _ in sites}
    assert "新错误" in texts
    assert any(text.startswith("失败: ") for text in texts)

    # Against an empty baseline, both sites are unbaselined.
    unbaselined = find_unbaselined(scanned, {})
    assert len(unbaselined) == 2

    # Baselining exactly the found hashes clears them; anything else still fires.
    known_hashes = [text_hash for _, _, text_hash in sites]
    baseline = {"core/example.py": known_hashes}
    assert find_unbaselined(scanned, baseline) == []

    # A stale baseline (missing one hash) still reports the other as unbaselined.
    partial_baseline = {"core/example.py": known_hashes[:1]}
    assert len(find_unbaselined(scanned, partial_baseline)) == 1

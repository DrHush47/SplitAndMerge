"""Сквозные smoke-тесты pipeline/sam.py через subprocess.

Запуск: [sys.executable, "pipeline/sam.py", ...] с cwd=корень репо.
Сеть не используется ни в одном кейсе (только --help, --dry-run и ошибки конфигурации).
Коды выхода сверены с реализацией main() в sam.py:
  0 — успех; 1 — есть REFUTED; 2 — ошибка конфигурации (argparse required → 2,
  неизвестные уровни → 2, read_targets/файл targets → 2).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SAM = REPO_ROOT / "pipeline" / "sam.py"
_ENV = {**os.environ, "PYTHONUTF8": "1"}

VALID_TARGET = [{"id": "ref01", "fact": "Example fact", "url": "https://example.com"}]


def run_sam(*args, timeout=120):
    """Запустить sam.py в корне репо, вернуть CompletedProcess (байты)."""
    return subprocess.run(
        [sys.executable, str(SAM), *map(str, args)],
        cwd=str(REPO_ROOT), env=_ENV,
        capture_output=True, timeout=timeout,
    )


def _write_targets(tmp_path, content):
    p = tmp_path / "targets.json"
    p.write_text(json.dumps(content), encoding="utf-8")
    return p


# --- 1) --help ---

def test_help_exit_zero():
    # argparse -h печатает help и завершается кодом 0
    r = run_sam("--help")
    assert r.returncode == 0


# --- 2) --dry-run не создаёт каталог вывода (проверка правки B1) ---

def test_dry_run_exit_zero_and_no_outdir(tmp_path):
    # main(): dry-run завершается sys.exit(0) ДО out_dir.mkdir (перенесено в боевой прогон)
    targets = _write_targets(tmp_path, VALID_TARGET)
    out_dir = tmp_path / "out"
    r = run_sam("--dry-run", "--targets", targets, "--out-dir", out_dir)
    assert r.returncode == 0
    assert not out_dir.exists(), "dry-run не должен создавать каталог вывода"


# --- 3) обязательный --targets ---

def test_missing_targets_exit_two():
    # argparse: required-аргумент отсутствует → код 2
    r = run_sam("--levels", "2")
    assert r.returncode == 2


# --- 4) неизвестный уровень ---

def test_invalid_levels_exit_two(tmp_path):
    # main(): unknown levels → FATAL → sys.exit(2)
    targets = _write_targets(tmp_path, VALID_TARGET)
    r = run_sam("--targets", targets, "--levels", "9")
    assert r.returncode == 2


# --- 5) несуществующий файл targets ---

def test_nonexistent_targets_exit_two(tmp_path):
    # main(): targets_path.is_file() → False → FATAL → sys.exit(2)
    r = run_sam("--targets", tmp_path / "no_such_file.json")
    assert r.returncode == 2


# --- 6) некорректное содержимое targets ---

def test_invalid_targets_content_exit_two(tmp_path):
    # read_targets: цель без обязательных полей id/fact/url → sys.exit(2)
    targets = _write_targets(tmp_path, [{"id": "ref01", "fact": "no url here"}])
    r = run_sam("--targets", targets)
    assert r.returncode == 2


def test_invalid_targets_json_exit_two(tmp_path):
    # read_targets: невалидный JSON → FATAL → sys.exit(2)
    p = tmp_path / "targets.json"
    p.write_text("{ this is not json", encoding="utf-8")
    r = run_sam("--targets", p)
    assert r.returncode == 2

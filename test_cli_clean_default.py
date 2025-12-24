import subprocess
import sys

def test_help_includes_no_clean_flag():
    proc = subprocess.run([sys.executable, 'main.py', '--help'], capture_output=True, text=True)
    assert proc.returncode == 0
    assert '--no-clean' in proc.stdout
    assert '--clean-only' in proc.stdout

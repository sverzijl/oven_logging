"""Run the dedicated boundary test file 3 times and the full suite once."""
import subprocess
import os

os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

# Dedicated boundary tests — run 3 times
for i in range(3):
    r = subprocess.run(
        ["python", "-m", "pytest", "tests/test_curve_boundary_detection.py", "-q", "--tb=line"],
        capture_output=True, text=True,
    )
    # Print just summary line
    tail = r.stdout.splitlines()[-10:] if r.stdout else []
    print(f"=== boundary run {i + 1} ===")
    print("\n".join(tail))

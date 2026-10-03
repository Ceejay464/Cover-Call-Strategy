"""Checks for the new local boundary, including original-file integrity."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LocalBoundaryTests(unittest.TestCase):
    def command(self, *args):
        return subprocess.run([sys.executable, *args], cwd=ROOT,
                              text=True, capture_output=True)

    def test_original_computational_files_retained(self):
        result = self.command("-m", "local.verify_originals")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_existing_outputs_not_overwritten(self):
        from local.common import prepare_output
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "previous"
            p.mkdir()
            marker = p / "important.txt"
            marker.write_text("previous results")
            with self.assertRaises(ValueError):
                prepare_output(p)
            self.assertEqual(marker.read_text(), "previous results")

    def test_daily_panel_does_not_silently_fill_missing_symbol(self):
        from local.common import load_panel
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "prices.csv"
            p.write_text("date,symbol,open,high,low,close\n"
                         "2023-01-02,A,1,1.1,0.9,1\n"
                         "2023-01-02,B,2,2.1,1.9,2\n"
                         "2023-01-03,A,1,1.1,0.9,1\n")
            with self.assertRaisesRegex(ValueError, "all symbols"):
                load_panel(p)

    def test_daily_panel_rejects_invalid_ohlc(self):
        from local.common import load_panel
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "prices.csv"
            p.write_text("date,symbol,open,high,low,close\n2023-01-02,A,1,0.8,0.9,1\n")
            with self.assertRaisesRegex(ValueError, "OHLC"):
                load_panel(p)


if __name__ == "__main__":
    unittest.main()

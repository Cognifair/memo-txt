import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parent / "cli.py"
SPEC = importlib.util.spec_from_file_location("memo_txt_cli", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CliTests(unittest.TestCase):
    def test_lint_dispatches(self):
        with patch.object(MODULE, "run", return_value=0) as run:
            self.assertEqual(MODULE.main(["lint", "x.txt", "--require-answer-line"]), 0)
        self.assertEqual(run.call_args.args[0], "lint_txt.py")
        self.assertEqual(run.call_args.args[1], ["x.txt", "--require-answer-line"])

    def test_finalize_passes_member(self):
        with patch.object(MODULE, "run", return_value=1) as run:
            self.assertEqual(MODULE.main(["finalize", "x.txt", "--member", "pro"]), 1)
        self.assertEqual(run.call_args.args[1], ["x.txt", "--member", "pro"])


if __name__ == "__main__":
    unittest.main()

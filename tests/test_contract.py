"""The contract: the AI Video Production OS registry shape."""

import io
import json
import unittest
from contextlib import redirect_stdout

from bdmvkit import __version__
from bdmvkit.__main__ import main


class TestContract(unittest.TestCase):
    def test_contract_json(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["contract", "--json"]), 0)
        c = json.loads(out.getvalue())
        for k in ("skill_id", "version", "contract_version", "provides", "dependencies", "not_provided"):
            self.assertIn(k, c)
        self.assertEqual((c["skill_id"], c["version"]), ("bdmvkit", __version__))
        tool_ids = [t["tool_id"] for t in c["tools"]]
        ids = [p["id"] for p in c["provides"]]
        self.assertEqual(len(ids), len(set(ids)))
        for p in c["provides"]:
            self.assertEqual(set(p), {"id", "lifecycle", "tool_id"})
            self.assertIn(p["lifecycle"], ("PROPOSED", "EXPERIMENTAL", "STABLE", "DEPRECATED", "RETIRED"))
            self.assertIn(p["tool_id"], tool_ids)
        self.assertFalse(c["execution"]["network"])


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER_MAIN = ROOT / "server" / "main.py"


class StaticHashRouteTests(unittest.TestCase):
    def test_encoded_hash_paths_redirect_to_spa_hash_routes(self):
        source = SERVER_MAIN.read_text(encoding="utf-8")

        self.assertIn("RedirectResponse", source)
        self.assertIn('raw_path.startswith(b"/%23")', source)
        self.assertIn('path.startswith("/%23")', source)
        self.assertIn('path.startswith("/#")', source)
        self.assertIn('target = f"/#{suffix or \'/\'}"', source)
        self.assertIn("status_code=307", source)


if __name__ == "__main__":
    unittest.main()

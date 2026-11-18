import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import validate as V

MS = [{"d": "2024", "cat": "ai", "t": "x", "src": "u", "st": "p"} for _ in range(3)]


class Story(unittest.TestCase):
    def run_check(self, code, D):
        err = []
        V.check_story(code, D, err)
        return err

    def test_missing_story_new_company_fails(self):
        self.assertTrue(self.run_check("newco", {"milestones": MS}))

    def test_missing_story_pending_company_passes(self):
        code = next(iter(V.STORY_PENDING)) if V.STORY_PENDING else None
        if code:
            self.assertEqual(self.run_check(code, {"milestones": MS}), [])

    def test_ok(self):
        self.assertEqual(self.run_check("newco", {"story": {"t": "AI", "cats": ["ai"]}, "milestones": MS}), [])

    def test_too_few(self):
        self.assertTrue(self.run_check("newco", {"story": {"t": "AI", "cats": ["ai"]}, "milestones": MS[:2]}))

    def test_blank_title(self):
        self.assertTrue(self.run_check("newco", {"story": {"t": " ", "cats": ["ai"]}, "milestones": MS}))


if __name__ == "__main__":
    unittest.main()

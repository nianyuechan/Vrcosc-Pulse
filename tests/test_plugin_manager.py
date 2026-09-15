import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from plugins.manager import PluginManager


class _FakePlugin:
    def __init__(self, name, requires=None):
        self.name = name
        self.version = "1.0.0"
        self.description = ""
        self.author = None
        self.homepage = None
        self.requires = requires or []
        self.activated = False
        self.enabled = False

    def activate(self, ctx):
        self.activated = True

    def deactivate(self):
        self.activated = False


class PluginDependencyTests(unittest.TestCase):
    def _manager(self):
        ctx = SimpleNamespace(app=None, main_window=None)
        return PluginManager(ctx)

    def test_missing_module_dependency_is_reported(self):
        pm = self._manager()
        p = _FakePlugin("A", requires=["definitely_not_a_real_module_xyz"])
        ok, missing = pm._check_dependencies(p)
        self.assertFalse(ok)
        self.assertEqual(missing[0]["dep"], "definitely_not_a_real_module_xyz")
        self.assertEqual(missing[0]["reason"], "missing")

    def test_disabled_plugin_dependency_is_reported(self):
        pm = self._manager()
        dep = _FakePlugin("DepPlugin")
        pm._register(dep)
        p = _FakePlugin("B", requires=["DepPlugin"])
        ok, missing = pm._check_dependencies(p)
        self.assertFalse(ok)
        self.assertEqual(missing[0]["reason"], "disabled")

    def test_enabled_plugin_dependency_satisfied(self):
        pm = self._manager()
        dep = _FakePlugin("DepPlugin")
        pm._register(dep)
        pm._active.add("DepPlugin")
        p = _FakePlugin("B", requires=["DepPlugin"])
        ok, missing = pm._check_dependencies(p)
        self.assertTrue(ok)
        self.assertEqual(missing, [])

    def test_stdlib_module_dependency_satisfied(self):
        pm = self._manager()
        p = _FakePlugin("C", requires=["json"])
        ok, missing = pm._check_dependencies(p)
        self.assertTrue(ok)

    def test_duplicate_name_skipped(self):
        pm = self._manager()
        pm._register(_FakePlugin("Same"))
        pm._register(_FakePlugin("Same"))
        self.assertEqual(len(pm.plugins), 1)

    def test_set_plugin_enabled_requires_deps(self):
        pm = self._manager()
        p = _FakePlugin("NeedsDep", requires=["definitely_not_a_real_module_xyz"])
        pm._register(p)
        ok, msg = pm.set_plugin_enabled("NeedsDep", True)
        self.assertFalse(ok)
        self.assertIn("pip install", msg)
        self.assertFalse(p.activated)


if __name__ == "__main__":
    unittest.main()

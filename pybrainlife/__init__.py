# ponytail: back-compat shim — `pybrainlife.*` redirects to `brainlife.*`.
# Remove once no downstream still imports the old name.
import importlib
import sys
from importlib.machinery import ModuleSpec
from importlib.abc import MetaPathFinder, Loader

_PREFIX = "pybrainlife"


class _Redirector(MetaPathFinder, Loader):
    def find_spec(self, name, path=None, target=None):
        if name == _PREFIX or name.startswith(_PREFIX + "."):
            return ModuleSpec(name, self)
        return None

    def create_module(self, spec):
        target = "brainlife" + spec.name[len(_PREFIX):]
        module = importlib.import_module(target)
        sys.modules[spec.name] = module
        return module

    def exec_module(self, module):
        pass


sys.meta_path.insert(0, _Redirector())

"""Nothing may be defined above a module's imports.

Python 3.14 evaluates annotations lazily (PEP 649), so a function defined above the
import of a type it annotates loads perfectly well there. Python 3.13 evaluates them at
def time and raises NameError, taking the whole integration down on import. CI runs both;
local development runs one. This test is what makes the difference visible locally.

It is deliberately structural rather than semantic: by the time a module has finished
importing, every name is bound, so typing.get_type_hints resolves happily and proves
nothing. Definition order is the thing that matters, so definition order is what is
checked.
"""
import ast
import os

import pytest

PACKAGE = "custom_components/edf_energy"


def _modules():
  for dirpath, dirnames, filenames in os.walk(PACKAGE):
    dirnames[:] = [d for d in dirnames if d != "__pycache__"]
    for name in sorted(filenames):
      if name.endswith(".py"):
        yield os.path.join(dirpath, name)


@pytest.mark.parametrize("path", sorted(_modules()))
def test_no_definition_sits_above_the_imports(path):
  tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)

  last_import = max(
    (node.lineno for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))),
    default=None,
  )
  if last_import is None:
    return

  early = [
    node for node in tree.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    and node.lineno < last_import
  ]

  assert not early, (
    f"{path}: {', '.join(n.name for n in early)} defined above the imports on line "
    f"{last_import}. On Python 3.13 any annotation referring to a name imported below "
    f"raises NameError at import time."
  )

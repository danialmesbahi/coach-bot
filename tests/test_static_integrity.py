import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def module_exports(path: Path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name): names.add(t.id)
    return names


def test_local_from_imports_exist():
    files = {p.parent.name + '.' + p.stem: p for p in (ROOT / 'app').rglob('*.py')}
    # Resolve the few explicit local imports used by the app.
    for path in (ROOT / 'app').rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module or not node.module.startswith('app.'):
                continue
            target = ROOT / (node.module.replace('.', '/') + '.py')
            if not target.exists():
                target = ROOT / (node.module.replace('.', '/') + '/__init__.py')
            assert target.exists(), f'missing local module: {node.module}'
            exports = module_exports(target)
            for alias in node.names:
                if alias.name in exports:
                    continue
                # `from app.db import repositories` imports a submodule from a package.
                submodule = target.parent / f'{alias.name}.py'
                assert submodule.exists(), f'{path}: {node.module} has no {alias.name}'

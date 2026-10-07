"""Keep fixed application diagnostics in both UI catalogues as code evolves.

Dynamic engineering values and source text are not translated by this contract.
Parameterized diagnostics use reviewed templates in web/i18n.js instead.
"""
import ast
import json
from pathlib import Path


def test_static_backend_diagnostics_have_both_ui_translations():
    root=Path(__file__).parents[2]
    locales={}
    for name in ('en','zh-CN'):
        text=(root/'web'/'locales'/(name+'.js')).read_text()
        locales[name]=json.loads(text.split('Object.freeze(',1)[1].rsplit(');',1)[0])
    missing=[]
    for module in (root/'backend'/'strata').glob('*.py'):
        for node in ast.walk(ast.parse(module.read_text())):
            if not isinstance(node,ast.Call) or not isinstance(node.func,ast.Name):
                continue
            name=node.func.id
            args=node.args[1:] if name in ('HTTPException','_require') else node.args if name in ('ValueError','DataValidationError') else []
            for argument in args:
                if isinstance(argument,ast.Constant) and isinstance(argument.value,str):
                    for locale in locales:
                        if argument.value not in locales[locale]:
                            missing.append(f'{module.name}:{node.lineno} {locale}: {argument.value}')
    assert not missing, '\n'.join(missing)

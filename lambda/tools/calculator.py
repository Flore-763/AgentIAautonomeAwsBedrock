"""
tools/calculator.py
=====================

Outil "calculatrice" : évalue une expression arithmétique simple.

⚠️ On n'utilise JAMAIS `eval()` sur une entrée fournie par le LLM (donc
indirectement dérivée du message utilisateur) : ce serait une porte
ouverte à l'exécution de code arbitraire dans le Lambda. On utilise à la
place le module standard `ast` pour ne parser et n'autoriser QUE des
nœuds strictement arithmétiques (nombres, + - * / ** %, parenthèses,
signe unaire). Toute autre construction (appel de fonction, import,
attribut, etc.) est rejetée.
"""

import ast
import operator

from langchain_core.tools import tool

# Table blanche des opérateurs autorisés : tout opérateur absent de cette
# table fait échouer l'évaluation (voir `_safe_eval`).
_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,  # ex: -5
    ast.UAdd: operator.pos,  # ex: +5
}


def _safe_eval(node: ast.AST):
    """Évalue récursivement un nœud AST, en n'autorisant que l'arithmétique de base."""

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Seuls les nombres sont autorisés dans l'expression.")

    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPERATORS:
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        return _ALLOWED_OPERATORS[type(node.op)](left, right)

    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPERATORS:
        return _ALLOWED_OPERATORS[type(node.op)](_safe_eval(node.operand))

    # Tout le reste (appel de fonction, nom de variable, import, etc.) est refusé.
    raise ValueError(f"Expression non autorisée : {ast.dump(node)}")


@tool
def calculator(expression: str) -> str:
    """
    Calcule le résultat d'une expression arithmétique.

    À utiliser quand l'utilisateur demande un calcul numérique
    (addition, soustraction, multiplication, division, puissance, modulo).

    Args:
        expression: Une expression mathématique, par exemple
            "12 * (3 + 4) / 2". Opérateurs supportés : + - * / ** % et
            les parenthèses.

    Returns:
        Le résultat du calcul sous forme de chaîne, ou un message
        d'erreur explicite si l'expression n'est pas valide.
    """
    try:
        parsed = ast.parse(expression, mode="eval")
        result = _safe_eval(parsed.body)
        return str(result)
    except (SyntaxError, ValueError, ZeroDivisionError, TypeError) as error:
        return f"Erreur de calcul : impossible d'évaluer '{expression}' ({error})"

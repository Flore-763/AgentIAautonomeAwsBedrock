"""
tests/test_calculator.py
==========================

`calculator` n'a aucune dépendance externe (pas de LLM, pas de réseau) :
c'est de l'arithmétique pure via `ast`. Les tests couvrent surtout le
whitelisting de sécurité (`_safe_eval`), qui est la partie la plus
sensible de cet outil (cf. le commentaire du module : jamais d'`eval()`
brut sur une entrée dérivée du LLM/utilisateur).
"""

from tools.calculator import calculator


def _run(expression: str) -> str:
    """Petit helper : un outil LangChain (@tool) s'invoque via .invoke(dict)."""
    return calculator.invoke({"expression": expression})


class TestOperationsValides:
    def test_addition(self):
        assert _run("2 + 3") == "5"

    def test_soustraction(self):
        assert _run("10 - 4") == "6"

    def test_multiplication(self):
        assert _run("6 * 7") == "42"

    def test_division(self):
        assert _run("9 / 2") == "4.5"

    def test_puissance(self):
        assert _run("2 ** 10") == "1024"

    def test_modulo(self):
        assert _run("17 % 5") == "2"

    def test_parentheses_et_priorite_des_operateurs(self):
        # Correspond à l'exemple de la docstring de l'outil.
        assert _run("12 * (3 + 4) / 2") == "42.0"

    def test_signe_unaire_negatif(self):
        assert _run("-5 + 10") == "5"

    def test_signe_unaire_positif(self):
        assert _run("+5") == "5"

    def test_nombres_flottants(self):
        assert _run("1.5 + 2.5") == "4.0"


class TestGestionErreurs:
    def test_division_par_zero(self):
        result = _run("1 / 0")
        assert "Erreur de calcul" in result

    def test_expression_syntaxiquement_invalide(self):
        result = _run("2 + * 3")
        assert "Erreur de calcul" in result

    def test_expression_vide(self):
        result = _run("")
        assert "Erreur de calcul" in result


class TestWhitelistDeSecurite:
    """
    Ces tests vérifient qu'AUCUNE construction Python autre que
    l'arithmétique de base ne peut s'exécuter — c'est la garantie de
    sécurité de cet outil (pas d'`eval()`), donc la partie la plus
    importante à couvrir.
    """

    def test_rejette_un_appel_de_fonction(self):
        # __import__('os') ne doit jamais pouvoir s'exécuter (l'expression
        # est simplement rejetée ; son texte peut apparaître tel quel dans
        # le message d'erreur, ça ne prouve pas qu'elle a été exécutée).
        result = _run("__import__('os').system('echo pwned')")
        assert "Erreur de calcul" in result
        assert "Expression non autorisée" in result

    def test_rejette_un_nom_de_variable(self):
        result = _run("x + 1")
        assert "Erreur de calcul" in result

    def test_rejette_une_chaine_de_caracteres(self):
        result = _run("'a' + 'b'")
        assert "Erreur de calcul" in result

    def test_rejette_un_attribut(self):
        result = _run("(1).__class__")
        assert "Erreur de calcul" in result

    def test_rejette_une_comprehension(self):
        result = _run("[x for x in range(10)]")
        assert "Erreur de calcul" in result


class TestOutilLangChain:
    """Vérifie que l'outil est bien exposé avec les métadonnées attendues par le LLM."""

    def test_nom_de_loutil(self):
        assert calculator.name == "calculator"

    def test_description_non_vide(self):
        assert calculator.description
        assert "calcul" in calculator.description.lower()

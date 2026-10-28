[project]
name = "@@PKG@@"
version = "0.1.0"
requires-python = ">=@@PYPROD@@"
dependencies = []

[tool.ruff]
line-length = 100
exclude = ["archive", ".venv"]

[tool.ruff.lint]
# Le réglage importe moins que l'obligation d'écrire POURQUOI.
# DJ tient ["F"] seulement, projet-a ["E","F","I","N","W","UP","B","SIM","S"].
# Les deux se défendent. Ce qui ne se défend pas : mettre une règle en `ignore`
# pour taire du bruit. Le jour où F821 est passé en ignore sur DJ, 22 vrais noms
# non définis sont partis en prod et le linter aveuglé n'a rien dit.
# Le bruit se corrige à la source, avec un noqa ciblé et justifié.
select = ["E", "F", "I", "N", "W", "UP", "B", "SIM", "S"]
ignore = []

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S101"]  # assert est le langage de pytest

[tool.pytest.ini_options]
testpaths = ["tests"]
# Trois étages séparés physiquement : unit, integration, regression.
# Le passage courant est unit + integration. La régression exige des fixtures
# générées et se lance à part.
markers = [
  "slow: sorti du passage rapide, gardé avant livraison. Un marqueur `slow` se justifie par des CHIFFRES : sur DJ, deux tests pesaient 325 s sur 379 s, soit 86 % de la suite.",
]
# Pas de seuil de couverture : c'est un choix à faire explicitement, pas à hériter.

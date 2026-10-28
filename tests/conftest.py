"""Fixtures partagées.

Les dépendances implicites deviennent explicites ici : tester la présence d'un
service AVANT pytest et prévenir « X absent, N tests vont échouer, ce n'est pas
une régression » évite de lire un service éteint comme un bug.
"""

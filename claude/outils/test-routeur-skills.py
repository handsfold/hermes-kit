#!/usr/bin/env python3
"""Regression sans LLM : motifs positifs/negatifs et catalogue Pi reel."""
import importlib.util
import json
from pathlib import Path
import re
import unittest

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('routeur', HERE / 'routeur-skills.py')
routeur = importlib.util.module_from_spec(spec)
spec.loader.exec_module(routeur)

CASES = {
 'ab-testing': (
  ['fais un test A/B sur le titre', 'teste deux versions du titre',
   'quelle variante convertit le mieux', 'laquelle des deux accroches marche'],
  ['vitest absents apres installation', 'deux versions de Python installees',
   'laquelle des deux commandes lance le serveur', 'compare deux fichiers']),
 'cro': (
  ['la page convertit mal', "beaucoup de visites et peu d'achats", 'le site vend moins',
   'augmente le taux de conversion de la page'],
  ['conversion WAV en MP3', 'conversion de dollars en bahts', 'conversion de degres Celsius',
   'friction dans le moteur']),
 'ai-seo': (
  ['etre cite par ChatGPT', 'ajoute un llms.txt', 'apparaitre dans les reponses IA',
   'etre cite par Perplexity', 'GEO pour mon site'],
  ['ouvre ChatGPT', 'change le modele de ChatGPT', 'demande la meteo a Perplexity',
   'geographie de Bangkok']),
 'nommer-marque': (
  ['trouve un nom pour ma marque', 'comment appeler ce nouveau produit',
   'quel nom donner a ma societe', 'un nom de domaine libre'],
  ['comment appeler cette fonction Python', 'comment appeler cette commande',
   'nomme une variable', 'redige un slogan']),
 'agent-reach': (
  ['cherche sur Reddit les avis', 'regarde cette video TikTok', 'lis ce lien et resume',
   "avis d'internautes sur ce service"],
  ['publie mon Short sur TikTok', 'programme la publication YouTube',
   'ajoute un bouton Reddit au site', 'connecte mon compte Twitter']),
 'animation-vocabulary': (
  ['Comment ça s’appelle quand le menu grandit depuis le bouton ?',
   'Quel est le nom de cet effet ?', 'Quel terme pour cette animation ?',
   'Comment s’appelle ce mouvement ?'],
  ['Ajoute une animation au menu', 'L’animation saccade sur mobile']),
 'pick-ui-library': (
  ['Quelle bibliothèque prendre pour un menu accessible ?',
   'Quoi utiliser pour les notifications ?', 'Quel composant UI pour un tiroir ?',
   'Quelle bibliothèque choisir pour le drag and drop ?', 'Je veux choisir une bibliothèque.'],
  ['J’aime les toasts animés', 'Fais une animation au menu', 'Swipe to dismiss a toast']),
 'implement': (
  ['/implement', 'Implémente ce ticket déjà validé', 'Implement this spec'],
  ['Fais un plan d’implémentation', 'Relis le diff depuis main']),
 'code-review': (
  ['Revue des normes pour la spec', 'Relis le diff depuis main', '/code-review'],
  ['Implémente ce ticket validé', 'Ajoute une animation au menu']),
 'animate': (
  ['Ajoute une animation au menu', 'Anime ce menu', 'Ce bouton manque de vie',
   'Fais une transition pour le bouton.'],
  ['Quel est le nom de cet effet ?', 'Le menu saccade sur mobile', 'Ajoute un swipe à la carte']),
 'animation-performance': (
  ['L’animation saccade sur mobile', 'Faut-il mettre will-change ?',
   'Le menu perd des images quand il bouge', 'Le menu rame pendant le scroll.'],
  ['Ajoute une animation au menu', 'Quel est le nom de cet effet ?', 'Ce bouton manque de vie']),
 'gestures': (
  ['Ajoute un swipe à la carte', 'Le tiroir suit mal le doigt',
   'Le geste bloque le défilement', 'Swipe to dismiss a toast', 'Drag to reorder a list.'],
  ['Crée un menu déroulant', 'L’animation saccade au menu', 'Quel est le nom de cet effet ?']),
 'marketing-ideas': (
  ['Idées de croissance pour ProjetA', 'Quoi tester pour attirer des clients à un logiciel ?',
   'SaaS : quelles pistes d’acquisition ?'],
  ['Idées de croissance pour MARQUE-E', 'Quel prix pour ProjetA ?',
   'Lance une campagne Google Ads pour ProjetA']),
 'marketing-council': (
  ['Simule un conseil marketing', 'Que diraient Ogilvy et Godin sur cette accroche ?',
   'Compare plusieurs avis sur cette stratégie marketing'],
  ['Lance une campagne Google Ads', 'Ajoute un slogan pour MARQUE-E',
   'Que dirait mon avocat de ce contrat ?']),
 'pricing': (
  ['Quel prix pour ProjetA ?', 'Comment fixer le tarif d’un logiciel SaaS ?',
   'ProjetA pricing abonnement'],
  ['Quel prix pour MARQUE-E ?', 'Lance Google Ads pour ProjetA',
   'Lance un test A/B du tarif']),
}


class RoutingTests(unittest.TestCase):
    def test_triggers(self):
        config = json.loads((HERE / 'declencheurs.json').read_text())
        for name, (positive, negative) in CASES.items():
            patterns = [re.compile(p, re.I) for p in config[name]['motifs']]
            for expected, messages in [(True, positive), (False, negative)]:
                for message in messages:
                    with self.subTest(skill=name, message=message):
                        self.assertEqual(any(p.search(message) for p in patterns), expected)

    def test_catalogue(self):
        skills = routeur.catalogue()
        self.assertGreater(len(skills), 20)
        self.assertEqual(len({s['name'] for s in skills}), len(skills))
        for skill in skills:
            self.assertTrue(Path(skill['path']).is_file())
        for query, expected in [('cro', 'cro'), ('nommer-marque','nommer-marque'),
                                ('llms.txt', 'ai-seo'), ('test A/B', 'ab-testing')]:
            with self.subTest(query=query):
                self.assertIn(expected, [s['name'] for s in routeur.chercher(skills, query)])
        self.assertEqual(routeur.chercher(skills, 'zzzznoexistingword'), [])
        self.assertLessEqual(len(routeur.chercher(skills,'page site',2)),2)


if __name__ == '__main__':
    unittest.main()

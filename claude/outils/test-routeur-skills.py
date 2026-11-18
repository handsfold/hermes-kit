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

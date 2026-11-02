import csv
import io
import os
import random
import tempfile
import unittest

from scie_holytek.cedule import cedule_mi_texte, feuille_operateur_html
from scie_holytek.lot import preparer_lot
from scie_holytek.optimiseur import ParametresScie, Stock, optimiser
from scie_holytek.regles import Morceau, Unite, charger_regles, evaluer, morceaux_pour_unite

ICI = os.path.dirname(__file__)
REGLES = charger_regles(os.path.join(ICI, "..", "regles_exemple.json"))
SANS_PERTE = ParametresScie(trait_scie=0, perte_debut=0, perte_fin=0, chute_min=300)


def m(longueur, materiel="P"):
    return Morceau(materiel=materiel, longueur=longueur, etiquette=f"{longueur}")


class TestFormules(unittest.TestCase):
    def test_arithmetique(self):
        self.assertEqual(evaluer("(L - 2*60 - N*70) / (N+1)", {"L": 1000, "N": 1}), 405)

    def test_refuse_le_code(self):
        for mauvais in ("__import__('os')", "L.real", "open('x')", "[1]"):
            with self.assertRaises(ValueError):
                evaluer(mauvais, {"L": 1})


class TestDeductions(unittest.TestCase):
    def test_fenetre_avec_un_meneau(self):
        unite = Unite("C1/F1", "fenetre_fixe_pvc", largeur=1200, hauteur=900, nb_meneaux_v=1)
        morceaux = morceaux_pour_unite(unite, REGLES)
        noms = [x.etiquette.split(" / ")[-1] for x in morceaux]
        self.assertEqual(noms.count("parclose horizontale"), 4)
        self.assertEqual(noms.count("meneau vertical"), 1)
        self.assertEqual(noms.count("soufflage vertical"), 0)  # pas de mur donné
        parclose = next(x for x in morceaux if x.etiquette.endswith("parclose horizontale"))
        self.assertEqual(parclose.longueur, (1200 - 120 - 70) / 2 - 2)
        self.assertEqual(parclose.materiel, "PARCLOSE-PVC-BLANC")

    def test_quantite_et_soufflage(self):
        unite = Unite("C1/F2", "fenetre_fixe_pvc", 800, 600, quantite=3, profondeur=150)
        noms = [x.etiquette for x in morceaux_pour_unite(unite, REGLES)]
        self.assertEqual(sum(n.endswith("soufflage vertical") for n in noms), 6)

    def test_produit_inconnu(self):
        with self.assertRaises(KeyError):
            morceaux_pour_unite(Unite("X", "inconnu", 1, 1), REGLES)


class TestOptimiseur(unittest.TestCase):
    def test_remplissage_parfait(self):
        # 6000 = 3000+2000+1000 et 6000 = 2500+2500+1000 : 2 barres, zéro perte
        morceaux = [m(x) for x in (3000, 2000, 1000, 2500, 2500, 1000)]
        res = optimiser(morceaux, [Stock("P", 6000)], SANS_PERTE)
        self.assertEqual(len(res.barres), 2)
        self.assertEqual(res.statistiques()["rebut_mm"], 0)

    def test_trait_de_scie_compte(self):
        params = ParametresScie(trait_scie=4, perte_debut=0, perte_fin=0, chute_min=300)
        # 2 x 3000 + 2 traits = 6008 > 6000 : il faut deux barres
        res = optimiser([m(3000), m(3000)], [Stock("P", 6000)], params)
        self.assertEqual(len(res.barres), 2)

    def test_chutes_utilisees_avant_barres_neuves(self):
        chute = Stock("P", 1200, reference="CH-1", emplacement="B3", quantite=1)
        res = optimiser([m(1100), m(4000)], [Stock("P", 6000), chute], SANS_PERTE)
        sources = {b.source.reference for b in res.barres}
        self.assertIn("CH-1", sources)
        self.assertEqual(res.statistiques()["chutes_utilisees"], 1)

    def test_chute_utilisee_une_seule_fois(self):
        chute = Stock("P", 1200, reference="CH-1", quantite=1)
        res = optimiser([m(1100), m(1100)], [Stock("P", 6000), chute], SANS_PERTE)
        self.assertEqual(sum(b.source.reference == "CH-1" for b in res.barres), 1)

    def test_chute_gardee_ou_rebut(self):
        res = optimiser([m(5000), m(5900)], [Stock("P", 6000)], SANS_PERTE)
        restes = sorted((b.reste, b.chute_gardee) for b in res.barres)
        self.assertEqual(restes, [(100, False), (1000, True)])

    def test_morceau_trop_long(self):
        res = optimiser([m(7000), m(100)], [Stock("P", 6000)], SANS_PERTE)
        self.assertEqual([x.longueur for x in res.non_places], [7000])

    def test_materiaux_separes(self):
        res = optimiser([m(1000, "A"), m(1000, "B")], [Stock("A", 6000), Stock("B", 6000)], SANS_PERTE)
        self.assertEqual(sorted(b.materiel for b in res.barres), ["A", "B"])

    def test_aucun_morceau_perdu_ni_double(self):
        hasard = random.Random(7)
        morceaux = [m(hasard.randint(200, 2500)) for _ in range(200)]
        params = ParametresScie()
        res = optimiser(morceaux, [Stock("P", 5800)], params)
        places = [x for b in res.barres for x in b.morceaux]
        self.assertEqual(sorted(map(id, places)), sorted(map(id, morceaux)))
        for b in res.barres:
            consomme = params.perte_debut + sum(x.longueur + params.trait_scie for x in b.morceaux)
            self.assertLessEqual(consomme, b.longueur_barre - params.perte_fin)
        self.assertLess(res.statistiques()["perte_pct"], 5)


class TestSorties(unittest.TestCase):
    def test_cedule_csv(self):
        res = optimiser([m(1000.5), m(800)], [Stock("P", 6000)], SANS_PERTE)
        lignes = list(csv.reader(io.StringIO(cedule_mi_texte(res)), delimiter=";"))
        self.assertEqual(lignes[0][:6], ["CHARGEMENT", "MATERIEL", "BARRE_NO", "BARRE_LONG", "NBPIECES", "INFO"])
        self.assertEqual(lignes[1][:6], ["1", "P", "1", "6000", "2", "NEUVE"])
        self.assertEqual(lignes[1][6:], ["1000,5", "800,0"])

    def test_feuille_operateur(self):
        res = optimiser([m(1000)], [Stock("P", 6000)], SANS_PERTE)
        page = feuille_operateur_html(res, "L-0001")
        self.assertIn("*L-0001*", page)
        self.assertIn("GARDER chute", page)

    def test_lot_complet(self):
        unites = [
            Unite("C9001/F1", "fenetre_fixe_pvc", 1200, 900, nb_meneaux_v=1, profondeur=150),
            Unite("C9001/F2", "fenetre_fixe_pvc", 600, 1500, quantite=2),
        ]
        chutes = [Stock("PARCLOSE-PVC-BLANC", 1500, reference="CH-9", quantite=1)]
        with tempfile.TemporaryDirectory() as dossier:
            res = preparer_lot(unites, REGLES, chutes, "L-0001", dossier)
            self.assertEqual(
                sorted(os.listdir(dossier)),
                ["L-0001-chutes.csv", "L-0001-feuille.html", "L-0001.csv"],
            )
        self.assertFalse(res.non_places)
        self.assertEqual(res.statistiques()["chutes_utilisees"], 1)


if __name__ == "__main__":
    unittest.main()

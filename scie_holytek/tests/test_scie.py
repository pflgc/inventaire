import csv
import io
import os
import random
import tempfile
import unittest

from scie_holytek.cedule import cedule_mi_texte, chargements, feuille_operateur_html, ligne_mi
from scie_holytek.lot import preparer_lot
from scie_holytek.optimiseur import ParametresScie, Stock, optimiser
from scie_holytek.regles import Morceau, Unite, charger_regles, evaluer, morceaux_pour_unite

ICI = os.path.dirname(__file__)
REGLES = charger_regles(os.path.join(ICI, "..", "regles_exemple.json"))
SANS_PERTE = ParametresScie(trait_scie=0, perte_debut=0, perte_fin=0, chute_min=300, empilage_defaut=1, correction_longueur=0)
EMPILE = ParametresScie(trait_scie=0, perte_debut=0, perte_fin=0, chute_min=300, empilage_defaut=2, correction_longueur=0)


def m(longueur, materiel="P", code=None):
    code = code or f"X-{longueur}"
    return Morceau(materiel=materiel, longueur=longueur, etiquette=code, code=code)


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
        params = ParametresScie(trait_scie=4, perte_debut=0, perte_fin=0, chute_min=300, empilage_defaut=1)
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
        params = ParametresScie(empilage_defaut=1)
        res = optimiser(morceaux, [Stock("P", 5800)], params)
        places = [x for b in res.barres for x in b.morceaux]
        self.assertEqual(sorted(map(id, places)), sorted(map(id, morceaux)))
        for b in res.barres:
            consomme = params.perte_debut + sum(x.longueur + params.trait_scie for x in b.morceaux)
            self.assertLessEqual(consomme, b.longueur_barre - params.perte_fin)
        self.assertLess(res.statistiques()["perte_pct"], 5)


class TestEmpilage(unittest.TestCase):
    def test_jumeaux_coupes_ensemble(self):
        # 2 x 3000 + 2 x 2900 : une seule passe de 2 barres empilées
        morceaux = [m(3000, code="A"), m(3000, code="B"), m(2900, code="C"), m(2900, code="D")]
        res = optimiser(morceaux, [Stock("P", 6000)], EMPILE)
        self.assertEqual(len(res.barres), 1)
        passe = res.barres[0]
        self.assertEqual(passe.empilage, 2)
        self.assertEqual([[x.longueur for x in c] for c in passe.copies], [[3000, 2900], [3000, 2900]])
        self.assertEqual(res.statistiques()["barres_neuves"], 2)
        champs = cedule_mi_texte(res, afficher_reste=False).split("\r\n")[0].split(";")
        self.assertEqual(champs[1:8], ["P", "6000", "2", "A / B", "3000", "C / D", "2900"])

    def test_morceau_sans_jumeau_coupe_seul(self):
        res = optimiser([m(1000), m(1000), m(1500)], [Stock("P", 6000)], EMPILE)
        self.assertEqual(sorted(p.empilage for p in res.barres), [1, 2])
        seule = next(p for p in res.barres if p.empilage == 1)
        self.assertEqual([x.longueur for x in seule.morceaux], [1500])

    def test_meneau_jamais_empile(self):
        morceaux = [m(1000, "MENEAU"), m(1000, "MENEAU"), m(1000, "PARCLOSE"), m(1000, "PARCLOSE")]
        stocks = [Stock("MENEAU", 6000, empilage=1), Stock("PARCLOSE", 6000)]
        res = optimiser(morceaux, stocks, EMPILE)
        empilages = {p.materiel: p.empilage for p in res.barres}
        self.assertEqual(empilages, {"MENEAU": 1, "PARCLOSE": 2})
        meneau = next(p for p in res.barres if p.materiel == "MENEAU")
        self.assertEqual(len(meneau.morceaux), 2)

    def test_paire_de_chutes(self):
        chutes = [Stock("P", 1300, reference="CH-1", quantite=1), Stock("P", 1250, reference="CH-2", quantite=1)]
        res = optimiser([m(1200), m(1200)], [Stock("P", 6000)] + chutes, EMPILE)
        passe = res.barres[0]
        self.assertEqual(sorted(s.reference for s in passe.sources), ["CH-1", "CH-2"])
        self.assertEqual(passe.longueur_barre, 1250)  # la plus courte des deux
        self.assertEqual(sorted(passe.restes), [50, 100])
        self.assertEqual(res.statistiques()["barres_neuves"], 0)

    def test_aucun_morceau_perdu_en_empilage(self):
        hasard = random.Random(11)
        morceaux = [m(hasard.choice([400, 650, 900, 1225, 1800, 2100])) for _ in range(151)]
        res = optimiser(morceaux, [Stock("P", 5800)], ParametresScie())
        places = [x for p in res.barres for c in p.copies for x in c]
        self.assertEqual(sorted(map(id, places)), sorted(map(id, morceaux)))
        for p in res.barres:
            longueurs = [[x.longueur for x in c] for c in p.copies]
            self.assertTrue(all(l == longueurs[0] for l in longueurs))


class TestBoutsSales(unittest.TestCase):
    def test_marges_par_materiau(self):
        # 2 x 2900 rentrent dans 6000 sans marge, plus avec 250 mm de bout sale à la fin
        stocks = [Stock("SALE", 6000, perte_fin=250), Stock("PROPRE", 6000)]
        morceaux = [m(2900, "SALE"), m(2900, "SALE"), m(2900, "PROPRE"), m(2900, "PROPRE")]
        res = optimiser(morceaux, stocks, SANS_PERTE)
        par_mat = {}
        for p in res.barres:
            par_mat[p.materiel] = par_mat.get(p.materiel, 0) + 1
        self.assertEqual(par_mat, {"SALE": 2, "PROPRE": 1})

    def test_jamais_moins_que_la_scie(self):
        params = ParametresScie(empilage_defaut=1)
        res = optimiser([m(4500)], [Stock("P", 4670, perte_debut=1)], params)
        self.assertEqual(res.non_places, [])
        res = optimiser([m(4540)], [Stock("P", 4670, perte_debut=1)], params)
        self.assertEqual(len(res.non_places), 1)  # 4540 + 3,5 + 6,35 + 127 > 4670


class TestEssaiReel(unittest.TestCase):
    """Constats de l'essai du soufflage 6 po (barre de 4670 mm)."""

    def setUp(self):
        ms = [m(L, "SOUFFLAGE 6PO", code=c) for L, c in [(1830, "72"), (1525, "60"), (915, "36")]]
        self.res = optimiser(ms, [Stock("SOUFFLAGE 6PO", 4670)], ParametresScie(empilage_defaut=1))
        self.champs = cedule_mi_texte(self.res).split(";")

    def test_seulement_le_bout_sale_coupe_en_premier(self):
        self.assertEqual(self.champs[0], "10")  # et non plus 383 (15,5 po jetés au début)

    def test_jamais_plus_de_3_po_et_demi_au_debut(self):
        with self.assertRaises(ValueError):
            ParametresScie(rognure_debut=100)
        res = optimiser([m(1000, "S")], [Stock("S", 4670, perte_debut=500)], ParametresScie(empilage_defaut=1))
        self.assertLessEqual(float(cedule_mi_texte(res).split(";")[0]), 88.9)

    def test_un_huitieme_ajoute_a_chaque_morceau(self):
        self.assertEqual(self.champs[5::2][:3], ["1833.175", "1528.175", "918.175"])

    def test_le_reste_sort_a_la_fin_cote_butee(self):
        passe = self.res.barres[0]
        self.assertGreaterEqual(passe.reste, 127)  # jamais une dernière coupe trop mince
        self.assertEqual(passe.reste, 369)


class TestSorties(unittest.TestCase):
    def test_format_mi_reel(self):
        """Relire la cédule d'essai Mec-Inov et la réécrire identique, octet pour octet."""
        with open(os.path.join(ICI, "donnees", "Mec-Inov_0822po.csv"), "rb") as f:
            original = f.read().decode("ascii")
        for ligne in original.split("\r\n")[:-1]:
            champs = ligne.split(";")
            paires = [c for c in champs[4:]]
            morceaux = [
                (paires[i], float(paires[i + 1])) for i in range(0, len(paires), 2) if paires[i]
            ]
            chargement = {
                "rognure": float(champs[0]),
                "materiel": champs[1],
                "longueur_barre": float(champs[2]),
                "nb": int(champs[3]),
                "morceaux": morceaux,
            }
            self.assertEqual(ligne_mi(chargement), ligne)

    def test_cedule_groupe_les_barres_identiques(self):
        morceaux = [m(3100, code="A"), m(2800, code="B"), m(3100, code="C"), m(2800, code="D")]
        res = optimiser(morceaux, [Stock("P", 6000)], SANS_PERTE)
        texte = cedule_mi_texte(res, afficher_reste=False)
        self.assertTrue(texte.endswith("\r\n"))
        lignes = texte.split("\r\n")[:-1]
        self.assertEqual(len(lignes), 1)
        champs = lignes[0].split(";")
        self.assertEqual(len(champs), 64)
        self.assertEqual(champs[:8], ["0", "P", "6000", "2", "A / C", "3100", "B / D", "2800"])

    def test_instruction_reste_sur_derniere_etiquette(self):
        rebut = optimiser([m(5900, code="A")], [Stock("P", 6000)], SANS_PERTE)
        garder = optimiser([m(3000, code="X"), m(2000, code="Y")], [Stock("P", 6000)], SANS_PERTE)
        self.assertEqual(cedule_mi_texte(rebut).split(";")[1:5], ["P", "6000", "1", "REBUT 100"])
        self.assertEqual(cedule_mi_texte(garder).split(";")[4:8], ["X", "3000", "GARDER 1000", "2000"])

    def test_aucun_texte_trop_long(self):
        longs = [m(1000, "UN MATERIAU AU NOM BEAUCOUP TROP LONG", code="C9019/F1 PARCLOSE >HAUT") for _ in range(4)]
        longs += [m(900, "UN MATERIAU AU NOM BEAUCOUP TROP LONG", code=f"C90{i}/F1 PH") for i in range(4)]
        res = optimiser(longs, [Stock("UN MATERIAU AU NOM BEAUCOUP TROP LONG", 6000)], EMPILE)
        for ligne in cedule_mi_texte(res, afficher_reste=False).split("\r\n")[:-1]:
            champs = ligne.split(";")
            self.assertLessEqual(len(champs[1]), 23)
            for etiquette in [e for e in champs[4::2] if e]:
                self.assertNotIn(">", etiquette)
                self.assertLessEqual(len(etiquette), 23)
                for partie in etiquette.split(" / "):
                    self.assertLessEqual(len(partie), 13, etiquette)

    def test_cedule_en_pouces(self):
        res = optimiser([m(1219.2, code="A")], [Stock("P", 2438)], SANS_PERTE)
        champs = cedule_mi_texte(res, unite="po").split(";")
        self.assertEqual(champs[2], "95.9843")
        self.assertEqual(champs[5], "48")

    def test_chute_seule_sur_sa_ligne(self):
        chute = Stock("P", 3000, reference="CH-1", quantite=1)
        res = optimiser([m(2900), m(2900)], [Stock("P", 3000), chute], SANS_PERTE)
        self.assertEqual([c["nb"] for c in chargements(res)], [1, 1])

    def test_max_30_morceaux_par_barre(self):
        res = optimiser([m(50) for _ in range(40)], [Stock("P", 6000)], SANS_PERTE)
        self.assertEqual(sorted(len(b.morceaux) for b in res.barres), [10, 30])

    def test_feuille_operateur(self):
        res = optimiser([m(1000)], [Stock("P", 6000)], SANS_PERTE)
        page = feuille_operateur_html(res, "L-0001")
        self.assertIn("*L-0001*", page)
        self.assertIn("GARDER chute", page)

    def test_nom_de_lot_court(self):
        from scie_holytek.lot import verifier_no_lot
        verifier_no_lot("L-0001")
        for mauvais in ("SOUFFLAGE-6PO-1BARRE", "L 0001", "L-0001 (4)"):
            with self.assertRaises(ValueError):
                verifier_no_lot(mauvais)

    def test_lot_complet(self):
        unites = [
            Unite("C9001/F1", "fenetre_fixe_pvc", 1200, 900, nb_meneaux_v=1, profondeur=150),
            Unite("C9001/F2", "fenetre_fixe_pvc", 600, 1500, quantite=2),
        ]
        chutes = [
            Stock("PARCLOSE-PVC-BLANC", 1500, reference="CH-9", quantite=1),
            Stock("PARCLOSE-PVC-BLANC", 1450, reference="CH-10", quantite=1),
        ]
        with tempfile.TemporaryDirectory() as dossier:
            res = preparer_lot(unites, REGLES, chutes, "L-0001", dossier)
            self.assertEqual(
                sorted(os.listdir(dossier)),
                ["L-0001-chutes.csv", "L-0001-feuille.html", "L-0001.csv"],
            )
        self.assertFalse(res.non_places)
        self.assertEqual(res.statistiques()["chutes_utilisees"], 2)


if __name__ == "__main__":
    unittest.main()

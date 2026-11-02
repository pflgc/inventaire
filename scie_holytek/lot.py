"""Préparer un lot de scie de bout en bout, en ligne de commande.

    python -m scie_holytek.lot unites.csv regles.json --lot L-0001 --sortie cedules/
        [--chutes chutes.csv]

unites.csv  : reference;type_produit;largeur;hauteur;quantite;nb_meneaux_v;nb_meneaux_h;profondeur;couleur
chutes.csv  : reference;materiel;longueur;emplacement

Produit dans --sortie :
    L-0001.csv            la cédule à déposer dans le dossier de MIEbouteuse
    L-0001-feuille.html   la feuille de l'opérateur, avec le code-barres du lot
    L-0001-chutes.csv     les nouvelles chutes à étiqueter et ranger
Dans Odoo, ce même enchaînement sera appelé par le bouton « Envoyer à la scie ».
"""
import argparse
import csv
import json
import os

from .cedule import cedule_mi_texte, feuille_operateur_html
from .optimiseur import ParametresScie, Stock, optimiser
from .regles import Unite, charger_regles, morceaux_pour_lot


def _lire_csv(chemin):
    with open(chemin, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def lire_unites(chemin):
    unites = []
    for ligne in _lire_csv(chemin):
        unites.append(
            Unite(
                reference=ligne["reference"],
                type_produit=ligne["type_produit"],
                largeur=float(ligne["largeur"]),
                hauteur=float(ligne["hauteur"]),
                quantite=int(ligne.get("quantite") or 1),
                nb_meneaux_v=int(ligne.get("nb_meneaux_v") or 0),
                nb_meneaux_h=int(ligne.get("nb_meneaux_h") or 0),
                profondeur=float(ligne.get("profondeur") or 0),
                couleur=ligne.get("couleur") or "",
            )
        )
    return unites


def lire_chutes(chemin):
    return [
        Stock(
            materiel=l["materiel"],
            longueur=int(float(l["longueur"])),
            reference=l["reference"],
            emplacement=l.get("emplacement", ""),
            quantite=1,
        )
        for l in _lire_csv(chemin)
    ]


def preparer_lot(unites, regles, chutes, no_lot, dossier):
    params = ParametresScie(**regles.get("parametres_scie", {}))
    barres_neuves = [Stock(materiel=b["materiel"], longueur=b["longueur"]) for b in regles["barres"]]
    morceaux = morceaux_pour_lot(unites, regles)
    resultat = optimiser(morceaux, barres_neuves + chutes, params)

    os.makedirs(dossier, exist_ok=True)
    # MIEbouteuse tourne sous Windows 7 : fichier ANSI, sans accents dans les étiquettes.
    with open(
        os.path.join(dossier, f"{no_lot}.csv"), "w", encoding="cp1252", errors="replace", newline=""
    ) as f:
        f.write(cedule_mi_texte(resultat, regles.get("unite_cedule", "mm")))
    with open(os.path.join(dossier, f"{no_lot}-feuille.html"), "w", encoding="utf-8") as f:
        f.write(feuille_operateur_html(resultat, no_lot))
    with open(os.path.join(dossier, f"{no_lot}-chutes.csv"), "w", encoding="utf-8", newline="") as f:
        ecrivain = csv.writer(f, delimiter=";")
        ecrivain.writerow(["reference", "materiel", "longueur", "emplacement"])
        numero = 1
        for barre in resultat.barres_ordonnees():
            if barre.chute_gardee:
                ecrivain.writerow([f"{no_lot}-CH{numero:03d}", barre.materiel, barre.reste, ""])
                numero += 1
    return resultat


def main(argv=None):
    parser = argparse.ArgumentParser(description="Préparer un lot de scie Holytek / MIEbouteuse")
    parser.add_argument("unites")
    parser.add_argument("regles")
    parser.add_argument("--lot", required=True)
    parser.add_argument("--sortie", default=".")
    parser.add_argument("--chutes")
    args = parser.parse_args(argv)

    regles = charger_regles(args.regles)
    chutes = lire_chutes(args.chutes) if args.chutes else []
    resultat = preparer_lot(lire_unites(args.unites), regles, chutes, args.lot, args.sortie)
    print(json.dumps(resultat.statistiques(), ensure_ascii=False, indent=2))
    if resultat.non_places:
        print(f"ATTENTION : {len(resultat.non_places)} morceau(x) plus long(s) que toute barre")


if __name__ == "__main__":
    main()

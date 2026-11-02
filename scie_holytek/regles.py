"""Déductions de coupe : d'une unité (fenêtre, porte) à la liste des morceaux.

Les règles vivent dans un fichier JSON (voir regles_exemple.json) pour que
Keven puisse les ajuster sans toucher au code. Chaque morceau est décrit par
une formule simple en millimètres, par exemple "L - 2*12" ou "(L - 40 - N*32) / (N+1)".

Variables disponibles dans les formules :
    L  largeur hors-tout de l'unité (mm)
    H  hauteur hors-tout de l'unité (mm)
    N  nombre de meneaux verticaux
    M  nombre de meneaux horizontaux (traverses)
    P  épaisseur du mur / profondeur du soufflage (mm), 0 si sans objet
"""
import ast
import json
import math
import operator
from dataclasses import dataclass, field

_OPERATEURS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
}
_FONCTIONS = {"max": max, "min": min, "arrondi": round, "plancher": math.floor}
VARIABLES = ("L", "H", "N", "M", "P")


def evaluer(formule, variables):
    """Évalue une formule arithmétique sans jamais exécuter de code arbitraire."""

    def _eval(noeud):
        if isinstance(noeud, ast.Expression):
            return _eval(noeud.body)
        if isinstance(noeud, ast.Constant) and isinstance(noeud.value, (int, float)):
            return noeud.value
        if isinstance(noeud, ast.Name) and noeud.id in variables:
            return variables[noeud.id]
        if isinstance(noeud, ast.BinOp) and type(noeud.op) in _OPERATEURS:
            return _OPERATEURS[type(noeud.op)](_eval(noeud.left), _eval(noeud.right))
        if isinstance(noeud, ast.UnaryOp) and type(noeud.op) in _OPERATEURS:
            return _OPERATEURS[type(noeud.op)](_eval(noeud.operand))
        if (
            isinstance(noeud, ast.Call)
            and isinstance(noeud.func, ast.Name)
            and noeud.func.id in _FONCTIONS
            and not noeud.keywords
        ):
            return _FONCTIONS[noeud.func.id](*[_eval(a) for a in noeud.args])
        raise ValueError(f"Formule non permise : {formule!r}")

    return _eval(ast.parse(str(formule), mode="eval"))


@dataclass
class Morceau:
    """Un morceau à couper, en millimètres, pointe à pointe."""

    materiel: str  # code du profilé + couleur, ex. "PARCLOSE-PVC-BLANC"
    longueur: float
    etiquette: str  # ex. "C9001-1016 / F1 / parclose haut"
    angle_g: int = 90
    angle_d: int = 90
    unite_ref: str = ""


@dataclass
class Unite:
    """Une fenêtre ou porte à produire."""

    reference: str  # ex. "C9001-1016 / F1"
    type_produit: str  # clé dans le fichier de règles
    largeur: float
    hauteur: float
    quantite: int = 1
    nb_meneaux_v: int = 0
    nb_meneaux_h: int = 0
    profondeur: float = 0
    couleur: str = ""
    options: dict = field(default_factory=dict)


def charger_regles(chemin):
    with open(chemin, encoding="utf-8") as f:
        return json.load(f)


def morceaux_pour_unite(unite, regles):
    """Retourne la liste des morceaux à couper pour une unité."""
    if unite.type_produit not in regles["produits"]:
        raise KeyError(f"Aucune règle de coupe pour le produit {unite.type_produit!r}")
    variables = {
        "L": unite.largeur,
        "H": unite.hauteur,
        "N": unite.nb_meneaux_v,
        "M": unite.nb_meneaux_h,
        "P": unite.profondeur,
    }
    morceaux = []
    for regle in regles["produits"][unite.type_produit]["morceaux"]:
        quantite = int(evaluer(regle.get("quantite", 1), variables)) * unite.quantite
        if quantite <= 0:
            continue
        longueur = round(evaluer(regle["longueur"], variables), 1)
        if longueur <= 0:
            raise ValueError(
                f"{unite.reference} : longueur négative pour {regle['nom']} ({longueur} mm)"
            )
        materiel = regle["profil"]
        couleur = unite.couleur or regle.get("couleur_defaut", "")
        if couleur:
            materiel = f"{materiel}-{couleur}"
        for i in range(quantite):
            morceaux.append(
                Morceau(
                    materiel=materiel,
                    longueur=longueur,
                    etiquette=f"{unite.reference} / {regle['nom']}",
                    angle_g=regle.get("angle_g", 90),
                    angle_d=regle.get("angle_d", 90),
                    unite_ref=unite.reference,
                )
            )
    return morceaux


def morceaux_pour_lot(unites, regles):
    morceaux = []
    for unite in unites:
        morceaux.extend(morceaux_pour_unite(unite, regles))
    return morceaux

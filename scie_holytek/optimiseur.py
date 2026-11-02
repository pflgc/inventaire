"""Optimisation des barres : placer les morceaux pour perdre le moins possible.

Principe, matériel par matériel :
1. On pige d'abord dans les chutes en inventaire, puis dans les barres neuves.
2. Chaque barre ouverte est remplie avec la combinaison de morceaux qui
   l'utilise le plus (sac à dos exact, au millimètre près).
3. Ce qui reste devient une chute gardée (si assez long) ou un rebut.

Tout est en millimètres entiers pour éviter les erreurs d'arrondi.
"""
from dataclasses import dataclass, field


@dataclass
class ParametresScie:
    trait_scie: int = 4  # épaisseur de lame, mm (À CONFIRMER)
    perte_debut: int = 10  # bout coupé pour équarrir la barre, mm (À CONFIRMER)
    perte_fin: int = 50  # bout que la butée ne peut pas pousser, mm (À CONFIRMER)
    chute_min: int = 300  # plus court que ça = rebut (À CONFIRMER)
    max_morceaux: int = 30  # limite d'une ligne de cédule MIEbouteuse


@dataclass
class Stock:
    """Une barre disponible : neuve (illimitée) ou chute en inventaire."""

    materiel: str
    longueur: int
    reference: str = ""  # numéro de chute, ex. "CH-0142"; vide pour une barre neuve
    emplacement: str = ""  # ex. "Rack B / case 3"
    quantite: int = 0  # 0 = illimité (barres neuves)

    @property
    def est_chute(self):
        return bool(self.reference)


@dataclass
class BarreCoupee:
    materiel: str
    longueur_barre: int
    morceaux: list
    source: Stock
    reste: int = 0
    chute_gardee: bool = False

    @property
    def utilise(self):
        return sum(int(round(m.longueur)) for m in self.morceaux)


@dataclass
class Resultat:
    barres: list = field(default_factory=list)
    non_places: list = field(default_factory=list)

    def par_materiel(self):
        groupes = {}
        for barre in self.barres:
            groupes.setdefault(barre.materiel, []).append(barre)
        return groupes

    def barres_ordonnees(self):
        """Les barres dans l'ordre de la cédule : par matériel, puis dans l'ordre de coupe."""
        return [b for _, barres in sorted(self.par_materiel().items()) for b in barres]

    def statistiques(self):
        total = sum(b.longueur_barre for b in self.barres)
        utile = sum(b.utilise for b in self.barres)
        gardees = sum(b.reste for b in self.barres if b.chute_gardee)
        rebut = total - utile - gardees
        return {
            "barres_neuves": sum(1 for b in self.barres if not b.source.est_chute),
            "chutes_utilisees": sum(1 for b in self.barres if b.source.est_chute),
            "longueur_totale_mm": total,
            "longueur_utile_mm": utile,
            "chutes_gardees_mm": gardees,
            "rebut_mm": rebut,
            "perte_pct": round(100 * rebut / total, 1) if total else 0.0,
        }


def _meilleur_remplissage(longueurs, capacite):
    """Sac à dos 0/1 exact : indices des morceaux qui remplissent le mieux la capacité.

    Utilise des entiers Python comme ensembles de bits : le bit c est à 1 si une
    somme de c mm est atteignable. On garde l'état après chaque morceau pour
    pouvoir retrouver la combinaison.
    """
    masque = (1 << (capacite + 1)) - 1
    etats = [1]
    for longueur in longueurs:
        etats.append((etats[-1] | (etats[-1] << longueur)) & masque)
    meilleur = etats[-1].bit_length() - 1
    choisis = []
    cible = meilleur
    for i in range(len(longueurs) - 1, -1, -1):
        if (etats[i] >> cible) & 1:
            continue  # atteignable sans le morceau i
        choisis.append(i)
        cible -= longueurs[i]
    return choisis


def _remplir(barre_long, morceaux, params):
    """Choisit les morceaux à couper dans une barre de longueur donnée."""
    # Chaque coupe consomme le morceau + un trait de scie.
    capacite = barre_long - params.perte_debut - params.perte_fin
    if capacite <= 0:
        return []
    poids = [int(round(m.longueur)) + params.trait_scie for m in morceaux]
    choisis = _meilleur_remplissage(poids, capacite)
    # Rare (morceaux très courts) : on garde les plus longs, le reste va à la barre suivante.
    return sorted(choisis, key=lambda i: -poids[i])[: params.max_morceaux]


def optimiser(morceaux, stocks, params=None):
    """Retourne un Resultat avec, pour chaque barre, les morceaux à y couper.

    morceaux : liste de regles.Morceau
    stocks   : liste de Stock (barres neuves et chutes), tous matériels confondus
    """
    params = params or ParametresScie()
    resultat = Resultat()
    par_materiel = {}
    for m in morceaux:
        par_materiel.setdefault(m.materiel, []).append(m)

    for materiel, restants in sorted(par_materiel.items()):
        restants = sorted(restants, key=lambda m: -m.longueur)
        chutes = sorted(
            [s for s in stocks if s.materiel == materiel and s.est_chute],
            key=lambda s: s.longueur,
        )
        neuves = sorted(
            [s for s in stocks if s.materiel == materiel and not s.est_chute],
            key=lambda s: -s.longueur,
        )
        disponibles_chutes = {id(c): c.quantite or 1 for c in chutes}

        while restants:
            barre = _prochaine_barre(restants, chutes, disponibles_chutes, neuves, params)
            if barre is None:
                resultat.non_places.extend(restants)
                break
            source, indices = barre
            if source.est_chute:
                disponibles_chutes[id(source)] -= 1
            places = [restants[i] for i in sorted(indices)]
            for i in sorted(indices, reverse=True):
                del restants[i]
            consomme = (
                params.perte_debut
                + sum(int(round(m.longueur)) + params.trait_scie for m in places)
            )
            reste = max(source.longueur - consomme, 0)
            resultat.barres.append(
                BarreCoupee(
                    materiel=materiel,
                    longueur_barre=source.longueur,
                    morceaux=sorted(places, key=lambda m: -m.longueur),
                    source=source,
                    reste=reste,
                    chute_gardee=reste >= params.chute_min,
                )
            )
    return resultat


def _prochaine_barre(restants, chutes, disponibles_chutes, neuves, params):
    """Choisit la prochaine barre à ouvrir et les morceaux à y placer.

    Une chute est prise si elle peut contenir au moins un morceau : on préfère
    vider l'inventaire de chutes. Sinon on prend la barre neuve qui laisse le
    moins de perte par mètre utilisé.
    """
    for chute in chutes:
        if disponibles_chutes[id(chute)] <= 0:
            continue
        indices = _remplir(chute.longueur, restants, params)
        if indices:
            return chute, indices

    meilleur = None
    for barre in neuves:
        indices = _remplir(barre.longueur, restants, params)
        if not indices:
            continue
        utilise = sum(int(round(restants[i].longueur)) for i in indices)
        taux = utilise / barre.longueur
        if meilleur is None or taux > meilleur[0]:
            meilleur = (taux, barre, indices)
    if meilleur:
        return meilleur[1], meilleur[2]
    return None

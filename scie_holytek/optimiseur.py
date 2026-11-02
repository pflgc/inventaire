"""Optimisation des barres : placer les morceaux pour perdre le moins possible.

À la Holytek, les barres sont presque toujours **empilées deux par deux** :
chaque coupe donne deux morceaux identiques. Les meneaux font exception et se
coupent une barre à la fois. L'empilage se règle par matériel (Stock.empilage).

Principe, matériel par matériel :
1. Empilage 2 : on forme des paires de morceaux de même longueur. Chaque
   « passe » coupe la même série de longueurs dans 2 barres à la fois.
   Un morceau sans jumeau est coupé seul, dans une passe à une barre.
2. On pige d'abord dans les chutes en inventaire (par paires de chutes pour
   l'empilage), puis dans les barres neuves.
3. Chaque passe est remplie avec la combinaison qui utilise le mieux la barre
   (sac à dos exact, au millimètre près).
4. Le bout restant de chaque barre devient une chute gardée ou un rebut.

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
    empilage_defaut: int = 2  # barres coupées l'une par-dessus l'autre


@dataclass
class Stock:
    """Une barre disponible : neuve (illimitée) ou chute en inventaire."""

    materiel: str
    longueur: int
    reference: str = ""  # numéro de chute, ex. "CH-0142"; vide pour une barre neuve
    emplacement: str = ""  # ex. "Rack B / case 3"
    quantite: int = 0  # 0 = illimité (barres neuves)
    empilage: int = 0  # 1 ou 2 barres par coupe; 0 = valeur par défaut de la scie

    @property
    def est_chute(self):
        return bool(self.reference)


@dataclass
class BarreCoupee:
    """Une passe à la scie : 1 ou 2 barres empilées, coupées pareil."""

    materiel: str
    longueur_barre: int  # longueur utile de la passe (la plus courte si 2 chutes)
    copies: list  # une liste de morceaux par barre de la passe, mêmes longueurs
    sources: list  # un Stock par barre de la passe
    restes: list = field(default_factory=list)  # bout restant de chaque barre, mm
    chute_min: int = 300

    @property
    def morceaux(self):
        return self.copies[0]

    @property
    def source(self):
        return self.sources[0]

    @property
    def empilage(self):
        return len(self.sources)

    @property
    def reste(self):
        return self.restes[0]

    @property
    def chute_gardee(self):
        return self.reste >= self.chute_min

    @property
    def utilise(self):
        return sum(int(round(m.longueur)) for m in self.morceaux)


@dataclass
class Resultat:
    barres: list = field(default_factory=list)  # les passes
    non_places: list = field(default_factory=list)

    def par_materiel(self):
        groupes = {}
        for barre in self.barres:
            groupes.setdefault(barre.materiel, []).append(barre)
        return groupes

    def barres_ordonnees(self):
        """Les passes dans l'ordre de la cédule : par matériel, puis dans l'ordre de coupe."""
        return [b for _, barres in sorted(self.par_materiel().items()) for b in barres]

    def statistiques(self):
        sources = [(s, r) for b in self.barres for s, r in zip(b.sources, b.restes)]
        total = sum(s.longueur for s, _ in sources)
        utile = sum(b.utilise * b.empilage for b in self.barres)
        gardees = sum(r for b in self.barres for r in b.restes if r >= b.chute_min)
        rebut = total - utile - gardees
        return {
            "passes": len(self.barres),
            "barres_neuves": sum(1 for s, _ in sources if not s.est_chute),
            "chutes_utilisees": sum(1 for s, _ in sources if s.est_chute),
            "longueur_totale_mm": total,
            "longueur_utile_mm": utile,
            "chutes_gardees_mm": gardees,
            "rebut_mm": rebut,
            "perte_pct": round(100 * rebut / total, 1) if total else 0.0,
        }


def _meilleur_remplissage(longueurs, capacite):
    """Sac à dos 0/1 exact : indices des éléments qui remplissent le mieux la capacité.

    Utilise des entiers Python comme ensembles de bits : le bit c est à 1 si une
    somme de c mm est atteignable. On garde l'état après chaque élément pour
    pouvoir retrouver la combinaison.
    """
    masque = (1 << (capacite + 1)) - 1
    etats = [1]
    for longueur in longueurs:
        etats.append((etats[-1] | (etats[-1] << longueur)) & masque)
    cible = etats[-1].bit_length() - 1
    choisis = []
    for i in range(len(longueurs) - 1, -1, -1):
        if (etats[i] >> cible) & 1:
            continue  # atteignable sans l'élément i
        choisis.append(i)
        cible -= longueurs[i]
    return choisis


def _remplir(barre_long, groupes, params):
    """Choisit les groupes (morceaux jumeaux) à couper dans une passe."""
    capacite = barre_long - params.perte_debut - params.perte_fin
    if capacite <= 0:
        return []
    # Chaque coupe consomme le morceau + un trait de scie.
    poids = [int(round(g[0].longueur)) + params.trait_scie for g in groupes]
    choisis = _meilleur_remplissage(poids, capacite)
    # Rare (morceaux très courts) : on garde les plus longs, le reste va à la passe suivante.
    return sorted(choisis, key=lambda i: -poids[i])[: params.max_morceaux]


def _jumeler(morceaux, empilage):
    """Forme des groupes de `empilage` morceaux de même longueur; retourne (groupes, orphelins)."""
    if empilage == 1:
        return [[m] for m in morceaux], []
    par_longueur = {}
    for m in morceaux:
        par_longueur.setdefault(int(round(m.longueur)), []).append(m)
    groupes, orphelins = [], []
    for liste in par_longueur.values():
        complets = len(liste) - len(liste) % empilage
        groupes += [liste[i : i + empilage] for i in range(0, complets, empilage)]
        orphelins += liste[complets:]
    return groupes, orphelins


def _lots_de_chutes(chutes, empilage):
    """Chutes regroupées par passe (paires de longueurs voisines si empilage 2)."""
    unites = sorted(
        (c for c in chutes for _ in range(c.quantite or 1)), key=lambda c: c.longueur
    )
    complets = len(unites) - len(unites) % empilage
    lots = [unites[i : i + empilage] for i in range(0, complets, empilage)]
    return lots, unites[complets:]


def _passes(groupes, lots_chutes, neuves, empilage, params, materiel):
    """Remplit des passes jusqu'à épuisement des groupes; retourne (passes, non placés)."""
    groupes = sorted(groupes, key=lambda g: -g[0].longueur)
    lots_chutes = list(lots_chutes)
    passes = []
    while groupes:
        choix = None
        for lot in lots_chutes:
            indices = _remplir(min(c.longueur for c in lot), groupes, params)
            if indices:
                choix = (lot, indices)
                lots_chutes.remove(lot)
                break
        if choix is None:
            meilleur = None
            for barre in neuves:
                indices = _remplir(barre.longueur, groupes, params)
                if not indices:
                    continue
                taux = sum(int(round(groupes[i][0].longueur)) for i in indices) / barre.longueur
                if meilleur is None or taux > meilleur[0]:
                    meilleur = (taux, [barre] * empilage, indices)
            if meilleur is None:
                break
            choix = (meilleur[1], meilleur[2])
        sources, indices = choix
        places = sorted((groupes[i] for i in indices), key=lambda g: -g[0].longueur)
        for i in sorted(indices, reverse=True):
            del groupes[i]
        consomme = params.perte_debut + sum(
            int(round(g[0].longueur)) + params.trait_scie for g in places
        )
        passes.append(
            BarreCoupee(
                materiel=materiel,
                longueur_barre=min(s.longueur for s in sources),
                copies=[[g[k] for g in places] for k in range(empilage)],
                sources=list(sources),
                restes=[max(s.longueur - consomme, 0) for s in sources],
                chute_min=params.chute_min,
            )
        )
    non_places = [m for g in groupes for m in g]
    return passes, non_places


def optimiser(morceaux, stocks, params=None):
    """Retourne un Resultat avec, pour chaque passe, les morceaux à y couper.

    morceaux : liste de regles.Morceau
    stocks   : liste de Stock (barres neuves et chutes), tous matériels confondus
    """
    params = params or ParametresScie()
    resultat = Resultat()
    par_materiel = {}
    for m in morceaux:
        par_materiel.setdefault(m.materiel, []).append(m)

    for materiel, liste in sorted(par_materiel.items()):
        neuves = [s for s in stocks if s.materiel == materiel and not s.est_chute]
        chutes = [s for s in stocks if s.materiel == materiel and s.est_chute]
        empilage = next((s.empilage for s in neuves if s.empilage), params.empilage_defaut)

        groupes, orphelins = _jumeler(liste, empilage)
        lots, chutes_seules = _lots_de_chutes(chutes, empilage)
        passes, non_places = _passes(groupes, lots, neuves, empilage, params, materiel)
        resultat.barres += passes
        resultat.non_places += non_places
        if orphelins:
            # Morceaux sans jumeau : une seule barre dans la scie.
            lots_seuls = [[c] for c in chutes_seules]
            passes, non_places = _passes([[m] for m in orphelins], lots_seuls, neuves, 1, params, materiel)
            resultat.barres += passes
            resultat.non_places += non_places
    return resultat

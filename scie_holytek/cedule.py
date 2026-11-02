"""Écriture des cédules pour MIEbouteuse (Mec-Inov) et de la feuille de l'opérateur.

Format MIEbouteuse, relevé sur la cédule d'essai Mec-Inov_0822po.csv :
    - pas d'en-tête, séparateur « ; », fins de ligne CRLF, ASCII, point décimal ;
    - une ligne par « chargement » = un groupe de barres identiques ;
    - toujours 64 champs : reste ; matériel ; longueur barre ; nb barres ;
      puis 30 paires étiquette ; longueur (cases vides au besoin) ;
    - reste : bout restant par barre (affiché seulement ; Mec-Inov y ajoute parfois
      une allocation selon le matériel, ex. AG 2x2 : 1.625 au lieu de 4.625) ;
    - quand plusieurs barres sont groupées, les étiquettes d'une même position
      sont jointes par « / » (ex. « MPPTC-0016 / MPPTC-0095 »).
"""
import html
import io

MAX_MORCEAUX = 30
MM_PAR_POUCE = 25.4


def _nombre(valeur):
    """Comme dans le fichier Mec-Inov : 96, 5.625, 45.6875."""
    texte = f"{valeur:.4f}".rstrip("0").rstrip(".")
    return texte or "0"


def _convertir(mm, unite):
    return mm / MM_PAR_POUCE if unite == "po" else mm


def _nettoyer(texte):
    return texte.replace(";", ",").replace("\r", " ").replace("\n", " ")


def chargements(resultat):
    """Regroupe les barres identiques (même matériel, longueur et coupes).

    Une chute en inventaire reste seule sur sa ligne : l'opérateur doit savoir
    laquelle prendre.
    """
    groupes = []
    index = {}
    for barre in resultat.barres_ordonnees():
        longueurs = tuple(m.longueur for m in barre.morceaux)
        cle = (barre.materiel, barre.longueur_barre, longueurs)
        if barre.source.est_chute or cle not in index:
            if not barre.source.est_chute:
                index[cle] = len(groupes)
            groupes.append({"materiel": barre.materiel, "longueur_barre": barre.longueur_barre,
                            "barres": [barre]})
        else:
            groupes[index[cle]]["barres"].append(barre)
    for groupe in groupes:
        barres = groupe["barres"]
        groupe["nb"] = len(barres)
        groupe["source"] = barres[0].source
        groupe["reste"] = barres[0].reste
        groupe["morceaux"] = []
        for position, morceau in enumerate(barres[0].morceaux):
            etiquettes = []
            for b in barres:
                e = b.morceaux[position].code
                if e not in etiquettes:
                    etiquettes.append(e)
            groupe["morceaux"].append((" / ".join(etiquettes), morceau.longueur))
    return groupes


def ligne_mi(chargement, unite="mm"):
    morceaux = chargement["morceaux"]
    if len(morceaux) > MAX_MORCEAUX:
        raise ValueError(f"MIEbouteuse accepte au plus {MAX_MORCEAUX} morceaux par barre")
    # Mec-Inov y met le reste calculé par son propre optimiseur ; nous, le vrai bout
    # restant après les traits de scie (ce que l'opérateur aura dans les mains).
    reste = chargement.get("reste", chargement["longueur_barre"] - sum(l for _, l in morceaux))
    champs = [
        _nombre(_convertir(reste, unite)),
        _nettoyer(chargement["materiel"]),
        _nombre(_convertir(chargement["longueur_barre"], unite)),
        str(chargement["nb"]),
    ]
    for etiquette, longueur in morceaux:
        champs += [_nettoyer(etiquette), _nombre(_convertir(longueur, unite))]
    champs += [""] * (64 - len(champs))
    return ";".join(champs)


def cedule_mi_texte(resultat, unite="mm"):
    return "".join(ligne_mi(c, unite) + "\r\n" for c in chargements(resultat))


def ecrire_cedule_mi(resultat, flux, unite="mm"):
    flux.write(cedule_mi_texte(resultat, unite))


def feuille_operateur_html(resultat, no_lot):
    """Feuille imprimable : code-barres du lot, barres à prendre, morceaux, chutes à garder."""
    stats = resultat.statistiques()
    rangs = []
    for no, ch in enumerate(chargements(resultat), start=1):
        source = ch["source"]
        prendre = (
            f"Chute {html.escape(source.reference)} {html.escape(source.emplacement)}"
            if source.est_chute
            else f"{ch['nb']} barre(s) neuve(s)"
        )
        morceaux = "<br>".join(
            f"{_nombre(l)} mm — {html.escape(e)}" for e, l in ch["morceaux"]
        )
        barre = ch["barres"][0]
        fin = f"GARDER chute {barre.reste} mm" if barre.chute_gardee else f"rebut {barre.reste} mm"
        rangs.append(
            f"<tr><td>{no}</td><td>{html.escape(ch['materiel'])}</td>"
            f"<td>{ch['longueur_barre']}</td><td>{prendre}</td><td>{morceaux}</td>"
            f"<td>{fin}{' (par barre)' if ch['nb'] > 1 else ''}</td></tr>"
        )
    non_places = "".join(
        f"<li>{html.escape(m.materiel)} — {_nombre(m.longueur)} mm — {html.escape(m.etiquette)}</li>"
        for m in resultat.non_places
    )
    alerte = f"<h2>Morceaux sans barre assez longue</h2><ul>{non_places}</ul>" if non_places else ""
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Lot {html.escape(no_lot)}</title>
<link href="https://fonts.googleapis.com/css2?family=Libre+Barcode+39&display=swap" rel="stylesheet">
<style>
body{{font-family:Arial,sans-serif;margin:16px}}
.code{{font-family:'Libre Barcode 39',monospace;font-size:64px}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #444;padding:4px;vertical-align:top}}
</style></head><body>
<h1>Lot de scie {html.escape(no_lot)}</h1>
<div class="code">*{html.escape(no_lot)}*</div>
<p>Barres neuves : {stats['barres_neuves']} · Chutes utilisées : {stats['chutes_utilisees']} ·
Perte : {stats['perte_pct']} %</p>
<table><tr><th>Charg.</th><th>Matériel</th><th>Long. barre</th><th>Prendre</th>
<th>Morceaux</th><th>Bout restant</th></tr>
{''.join(rangs)}</table>{alerte}
</body></html>"""

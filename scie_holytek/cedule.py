"""Écriture des cédules pour MIEbouteuse (Mec-Inov) et de la feuille de l'opérateur.

FORMAT PROVISOIRE : on a seulement vu les colonnes à l'écran de MIEbouteuse
(FAIT, BARRE_NO, BARRE_LONG, CHAR..., NBPIECES, INFO..., et d'autres cachées).
Dès qu'on a un vrai fichier .csv de la scie, on ajuste FORMAT_MI ci-dessous
et le test test_format_mi_reel. Rien d'autre ne devrait changer.
"""
import csv
import html
import io

FORMAT_MI = {
    "separateur": ";",
    "encodage": "cp1252",  # Windows 7 en français : à confirmer avec un vrai fichier
    "entete": True,
    "decimales": 1,
}


def _mm(valeur):
    texte = f"{valeur:.{FORMAT_MI['decimales']}f}"
    return texte.replace(".", ",") if FORMAT_MI["separateur"] == ";" else texte


def lignes_cedule(resultat):
    """Une ligne par barre, regroupées par chargement (= un matériel)."""
    lignes = []
    for no_chargement, (materiel, barres) in enumerate(
        sorted(resultat.par_materiel().items()), start=1
    ):
        for no_barre, barre in enumerate(barres, start=1):
            info = barre.source.reference or "NEUVE"
            if barre.source.emplacement:
                info += f" ({barre.source.emplacement})"
            lignes.append(
                {
                    "CHARGEMENT": no_chargement,
                    "MATERIEL": materiel,
                    "BARRE_NO": no_barre,
                    "BARRE_LONG": barre.longueur_barre,
                    "NBPIECES": len(barre.morceaux),
                    "INFO": info,
                    "PIECES": [m.longueur for m in barre.morceaux],
                    "ETIQUETTES": [m.etiquette for m in barre.morceaux],
                }
            )
    return lignes


def ecrire_cedule_mi(resultat, flux):
    """Écrit la cédule CSV que MIEbouteuse ouvrira (format provisoire)."""
    lignes = lignes_cedule(resultat)
    nb_max = max((len(l["PIECES"]) for l in lignes), default=0)
    ecrivain = csv.writer(flux, delimiter=FORMAT_MI["separateur"], lineterminator="\r\n")
    if FORMAT_MI["entete"]:
        ecrivain.writerow(
            ["CHARGEMENT", "MATERIEL", "BARRE_NO", "BARRE_LONG", "NBPIECES", "INFO"]
            + [f"LONG{i}" for i in range(1, nb_max + 1)]
        )
    for l in lignes:
        ecrivain.writerow(
            [l["CHARGEMENT"], l["MATERIEL"], l["BARRE_NO"], l["BARRE_LONG"], l["NBPIECES"], l["INFO"]]
            + [_mm(p) for p in l["PIECES"]]
        )


def cedule_mi_texte(resultat):
    flux = io.StringIO()
    ecrire_cedule_mi(resultat, flux)
    return flux.getvalue()


def feuille_operateur_html(resultat, no_lot):
    """Feuille imprimable : code-barres du lot, barres à prendre, morceaux, chutes à garder."""
    stats = resultat.statistiques()
    rangs = []
    for ligne, barre in zip(lignes_cedule(resultat), resultat.barres_ordonnees()):
        morceaux = "<br>".join(
            f"{_mm(m.longueur)} mm — {html.escape(m.etiquette)}" for m in barre.morceaux
        )
        if barre.chute_gardee:
            fin = f"GARDER chute {barre.reste} mm"
        else:
            fin = f"rebut {barre.reste} mm"
        rangs.append(
            "<tr>"
            f"<td>{ligne['CHARGEMENT']}</td><td>{html.escape(ligne['MATERIEL'])}</td>"
            f"<td>{ligne['BARRE_NO']}</td><td>{ligne['BARRE_LONG']}</td>"
            f"<td>{html.escape(ligne['INFO'])}</td><td>{morceaux}</td><td>{fin}</td>"
            "</tr>"
        )
    non_places = "".join(
        f"<li>{html.escape(m.materiel)} — {_mm(m.longueur)} mm — {html.escape(m.etiquette)}</li>"
        for m in resultat.non_places
    )
    alerte = (
        f"<h2>Morceaux sans barre assez longue</h2><ul>{non_places}</ul>" if non_places else ""
    )
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Lot {html.escape(no_lot)}</title>
<style>
body{{font-family:Arial,sans-serif;margin:16px}}
.code{{font-family:'Libre Barcode 39',monospace;font-size:64px}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #444;padding:4px;vertical-align:top}}
</style>
<link href="https://fonts.googleapis.com/css2?family=Libre+Barcode+39&display=swap" rel="stylesheet">
</head><body>
<h1>Lot de scie {html.escape(no_lot)}</h1>
<div class="code">*{html.escape(no_lot)}*</div>
<p>Barres neuves : {stats['barres_neuves']} · Chutes utilisées : {stats['chutes_utilisees']} ·
Perte : {stats['perte_pct']} %</p>
<table><tr><th>Charg.</th><th>Matériel</th><th>Barre</th><th>Long.</th><th>Prendre</th>
<th>Morceaux</th><th>Bout restant</th></tr>
{''.join(rangs)}</table>{alerte}
</body></html>"""

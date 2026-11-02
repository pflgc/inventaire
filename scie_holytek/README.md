# Scie Holytek + butée Mec-Inov (MIEbouteuse) — optimiseur de coupe

But : couper parclose, soufflage, boiserie et meneau **automatiquement**, avec le
moins de perte possible, et suivre les chutes et les rebuts. Odoo prépare tout,
MIEbouteuse ne fait que pousser et couper.

## Ce que fait ce dossier

| Fichier | Rôle |
|---|---|
| `regles.py` | Déductions : d'une fenêtre (L, H, meneaux, mur) à la liste des morceaux. Formules sécuritaires, modifiables sans code. |
| `regles_exemple.json` | Règles par type de produit, longueurs de barres, trait de scie, chute minimale. **Chiffres d'exemple, À CONFIRMER.** |
| `optimiseur.py` | Place les morceaux dans les barres : chutes en inventaire d'abord, puis barres neuves, remplissage exact au mm. |
| `cedule.py` | Écrit la cédule CSV pour MIEbouteuse et la feuille de l'opérateur (code-barres du lot). **Format CSV provisoire.** |
| `lot.py` | Tout l'enchaînement en une commande. |
| `essai/ESSAI-LGC-mm.csv` | Cédule d'essai à ouvrir dans MIEbouteuse en **Mode Manuel** seulement. |
| `tests/` | 21 tests (dont la relecture octet pour octet de la cédule Mec-Inov `tests/donnees/Mec-Inov_0822po.csv`) : `python3 -m unittest scie_holytek.tests.test_scie` |

Essai sur 25 fenêtres fictives : **1,6 % de perte** (et 20 m de chutes gardées en
inventaire), contre **14 %** en coupant les morceaux au fur et à mesure.

```
python3 -m scie_holytek.lot unites.csv scie_holytek/regles_exemple.json --lot L-0001 --sortie cedules/ [--chutes chutes.csv]
```

## Comment ça roulera à l'usine

1. Dans Odoo : choisir les commandes du lot de scie → **Envoyer à la scie**.
2. Odoo calcule les morceaux (déductions), optimise, et dépose `L-0001.csv` dans le
   dossier des cédules. Dans MIEbouteuse, **Configurer → Général → Répertoire des
   cédules** pointe vers un dossier à nous (ex. `P:\Odoo\FichiersDeScie\Holytek\`),
   donc pas besoin de droit admin sur `C:\Mec-Inov`.
3. Odoo imprime la feuille du lot avec son **code-barres**.
4. À la scie : **Ouvrir** → scanner le code-barres (le lecteur tape le nom du
   fichier + Entrée) → **Coupe automatique** → **Production**.
5. Chaque bout restant ≥ chute minimale est étiqueté (Zebra) et rangé ; Odoo l'ajoute
   à l'inventaire des chutes et le repige au prochain lot. Le reste sort en rebut.

## Ce qui manque avant la première coupe réelle

1. ~~Format CSV de MIEbouteuse~~ : **fait**, relevé sur la cédule d'essai Mec-Inov
   (64 champs : reste ; matériel ; longueur barre ; nb barres ; 30 × étiquette ; longueur).
   Reste à savoir si la scie est réglée en **mm ou en pouces** (`unite_cedule`).
2. **Onglet Configurer → Production** de MIEbouteuse : trait de scie, pertes de bout.
3. **Par profilé** : longueur des barres, angle de coupe, chute minimale.
4. **Déductions réelles** (Keven) pour chaque type de produit : remplacer les
   chiffres d'exemple de `regles_exemple.json`.
5. Premier essai : cédule ouverte en **Mode Manuel**, Coupe automatique à OFF,
   vérifier les longueurs avant de couper.

## Branchement dans Odoo (module `lgc_production`, dépôt lgc-odoo)

Le module a déjà `lgc.lot.scie` et le bouton `action_fichiers_scie` pour la PRODS20.
Plan pour ajouter la Holytek :

- **Code** : copier `regles.py`, `optimiseur.py`, `cedule.py` dans
  `lgc_production/scie_holytek/` (aucune dépendance externe, Python pur).
- **Modèles** :
  - `lgc.scie.machine` : PRODS20, Holytek ; format de sortie (`.txt` PRODS20,
    `.csv` MIEbouteuse) ; dossier de dépôt ; paramètres (trait, pertes, chute min).
  - `lgc.scie.profil` : matériel (profilé + couleur), longueur de barre, produit
    Odoo lié (pour le stock des barres neuves).
  - `lgc.scie.regle` : type de produit → morceaux (nom, profil, formule de longueur,
    formule de quantité, angles). Remplace le JSON, éditable par Keven.
  - `lgc.scie.chute` : référence, profil, longueur, emplacement, état
    (disponible / réservée / utilisée / rebutée), lot d'origine.
  - Sur `lgc.lot.scie` : machine, barres prévues, % de perte, rebuts.
- **Stock** : à l'envoi, réserver les barres neuves et les chutes ; à « Coupé »,
  consommer, créer les chutes gardées, sortir les rebuts (`stock.scrap`) avec raison.
- **Rebut accidentel** : bouton sur le lot (raison : mauvaise coupe, défaut,
  égratignure) → le morceau est remis dans le prochain lot.
- **Rapport** : % de perte et $ de rebuts par semaine, profilé, opérateur ; chutes
  qui dorment depuis plus de 90 jours.
- **Pont scie** : même mécanisme que pour la PRODS20, avec un 2ᵉ dossier.

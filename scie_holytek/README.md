# Scie Holytek + butée Mec-Inov (MIEbouteuse) — optimiseur de coupe

But : couper parclose, soufflage, boiserie et meneau **automatiquement**, avec le
moins de perte possible, et suivre les chutes et les rebuts. Odoo prépare tout,
MIEbouteuse ne fait que pousser et couper.

## Ce que fait ce dossier

| Fichier | Rôle |
|---|---|
| `regles.py` | Déductions : d'une fenêtre (L, H, meneaux, mur) à la liste des morceaux. Formules sécuritaires, modifiables sans code. |
| `regles_exemple.json` | Règles par type de produit, longueurs de barres, trait de scie, chute minimale. **Chiffres d'exemple, À CONFIRMER.** |
| `optimiseur.py` | Place les morceaux dans les barres : **2 barres empilées par coupe** (sauf meneaux : 1), morceaux jumelés par longueur, chutes en inventaire d'abord (par paires), puis barres neuves, remplissage exact au mm. |
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

## Demandes de l'usine (2 nov.) : retailles, coupe tardive, modifications

### 1. Inventaire des retailles et « quoi charger » (même principe que Protomach)
- Chaque retaille ≥ chute minimale reçoit un numéro (`CH-0142`), une longueur et un
  emplacement (rack / case), imprimés sur une étiquette Zebra au moment de la coupe.
- L'optimiseur pige d'abord dans les retailles (par paires si empilées).
- **À la scie** : le champ Matériel affiche `CH-0142 SOUFFLAGE 6PO` (fait,
  testé) ; la feuille du lot dit où la trouver (`B3`). Une barre neuve affiche
  seulement le matériel. Le dernier morceau dit quoi faire du reste
  (`GARDER 369` / `REBUT 73`).
- **Dans Odoo** : modèle `lgc.scie.chute` (disponible / réservée / utilisée /
  rebutée), scan de l'étiquette pour confirmer qu'on a pris la bonne, rapport des
  retailles qui dorment.

### 2. Soufflage et boiserie coupés le plus tard possible
Le client change souvent d'idée (soufflage 6 po → 9 po). Donc :
- Ces profilés ne sont **pas** mis dans un lot de scie à la confirmation de la vente.
- Le lot de finition est créé quand les fenêtres de la commande sont presque toutes
  terminées (ex. ≥ 80 % des unités soudées, ou date de livraison à J-3 : seuil à
  choisir).
- Les longueurs sont **recalculées au moment de créer le lot**, à partir de la
  commande telle qu'elle est ce jour-là (largeur de soufflage, couleur, options).
- Liste « Prêt à couper » dans Odoo : commandes dont la finition peut partir.

### 3. Modifier, ajouter, créditer facilement
`modifier_lot()` (fait, testé) :
- les passes **déjà coupées** ne bougent pas ;
- les morceaux retirés pas encore coupés disparaissent, les ajouts sont ajoutés,
  tout le reste est ré-optimisé et une nouvelle cédule est générée ;
- un morceau retiré **déjà coupé** est retourné « à créditer » et devient une
  retaille en inventaire (`pieces_en_inventaire()`), réutilisable au prochain lot
  ou pour la vente comptoir.
Dans Odoo : boutons *Ajouter une fenêtre*, *Retirer*, *Changer le soufflage* sur le
lot, qui appellent `modifier_lot()` et redéposent la cédule.

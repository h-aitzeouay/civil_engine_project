# INGENIERIE.COM — Journal des règles permanentes

## Version stable actuelle
0.21.7B

## Règles de dessin et de conception enregistrées

### Fondations
- Aucune semelle ne doit être supprimée automatiquement.
- Toute fondation finale doit être basée sur final_foundations.
- Les anciennes configurations ne doivent pas être superposées à la configuration finale.
- Les semelles excentrées périphériques ne doivent pas déborder de l'emprise.
- Si deux semelles interfèrent, étudier semelle combinée ou radier local.
- Si plusieurs interférences apparaissent, garder ouverte l'option radier général.
- Les poteaux doivent être entièrement portés par les fondations.
- Si le support du poteau n'est pas possible, afficher une alerte sans supprimer la fondation.

### Poteaux
- Les poteaux de rive doivent être interprétés comme poteaux effectifs à l'intérieur de l'emprise.
- Les désignations P01, P02, etc. doivent être placées hors semelles.
- Les labels poteaux doivent avoir une ligne de renvoi si déplacés.

### Axes
- Les axes de construction sont en pointillé.
- Les axes ne doivent pas traverser les bulles.
- Les bulles horizontales sont numérotées.
- Les bulles verticales sont alphabétiques.
- Les cotations doivent éviter les textes techniques.

### Ferraillage
- Les annotations Inf/Sup ne doivent pas chevaucher les bulles.
- Les annotations Inf/Sup ne doivent pas chevaucher les semelles.
- Les annotations Inf/Sup ne doivent pas toucher les contours des semelles.
- Les annotations Inf/Sup ne doivent pas chevaucher les poteaux.
- Les annotations Inf/Sup ne doivent pas entrer dans le tableau.
- Toute annotation technique doit passer par le gestionnaire anti-chevauchement.

### Poinçonnement
- Le poinçonnement doit être basé uniquement sur la configuration finale.
- Les anciennes semelles ne doivent pas être affichées.
- Les périmètres de poinçonnement doivent être discrets et ne pas ressembler à des semelles.

### Prochaine étape
- Générer les attentes poteaux.
- Générer des coupes types SI / SE / SC / RL.
- Ajouter tableau des attentes.
- Garder le tout en prédimensionnement à vérifier.

## Version 0.22.1
- Ajout des cadres poteaux dans les coupes types.
- Ajout de l'espacement des cadres :
  - zone serrée près de la fondation ;
  - zone courante au-dessus.
- Tableau des attentes enrichi :
  - forme des attentes ;
  - forme des cadres ;
  - dimensions intérieures des cadres ;
  - diamètre des cadres ;
  - espacement des cadres ;
  - longueur d'ancrage indicative.
- Les formes sont représentées graphiquement dans le tableau.

## Version 0.23.0
- Ajout de la vérification finale de cohérence du ferraillage.
- Vérification par fondation :
  - As fourni >= As requis ;
  - diamètre minimal ;
  - espacement maximal ;
  - rho réel pour le poinçonnement final.
- Ajout endpoint :
  - POST /reinforcement-final-check
- Cette étape prépare le poinçonnement final avec rho_l réel.

## Version 0.24.0
- Ajout de la vérification finale du poinçonnement.
- Le poinçonnement final utilise rho_l réel issu de /reinforcement-final-check.
- Ajout endpoint :
  - POST /punching-final
- Le rapport indique :
  - rho_l réel utilisé ;
  - vEd ;
  - vRdc ;
  - taux d'utilisation ;
  - statut OK / WARNING / NOT_OK par fondation et par poteau.

## Version 0.25.0
- Ajout du calcul indicatif des ancrages et recouvrements.
- Ajout endpoints :
  - POST /anchorage-details
  - POST /anchorage-details-dxf
- Ajout détails types :
  - Forme A : attente droite ;
  - Forme B : attente coudée / crosse ;
  - Forme C : recouvrement.
- Tableau par poteau :
  - attentes ;
  - cadres ;
  - dimensions cadre ;
  - Lbd ;
  - L0 ;
  - forme recommandée.

## Version 0.25.0
- Ajout du calcul indicatif des ancrages et recouvrements.
- Ajout endpoints :
  - POST /anchorage-details
  - POST /anchorage-details-dxf
- Ajout détails types :
  - Forme A : attente droite ;
  - Forme B : attente coudée / crosse ;
  - Forme C : recouvrement.
- Tableau par poteau :
  - attentes ;
  - cadres ;
  - dimensions cadre ;
  - Lbd ;
  - L0 ;
  - forme recommandée.

## Version 0.25.0
- Ajout du calcul indicatif des ancrages et recouvrements.
- Ajout endpoints :
  - POST /anchorage-details
  - POST /anchorage-details-dxf
- Ajout détails types :
  - Forme A : attente droite ;
  - Forme B : attente coudée / crosse ;
  - Forme C : recouvrement.
- Tableau par poteau :
  - attentes ;
  - cadres ;
  - dimensions cadre ;
  - Lbd ;
  - L0 ;
  - forme recommandée.

## Version 0.26.0
- Ajout des coupes détaillées SI / SE / SC / RL.
- Ajout endpoint :
  - POST /foundation-sections-dxf
- Les coupes affichent :
  - béton de propreté ;
  - semelle/radier ;
  - poteau ;
  - attentes ;
  - cadres poteaux ;
  - nappe inférieure ;
  - nappe supérieure ;
  - enrobage ;
  - cotations verticales ;
  - cotation largeur de coupe ;
  - tableau récapitulatif.

## Version 0.26.1
- Correction anti-chevauchement dans les coupes détaillées.
- Les annotations Nappe inf. et Nappe sup. doivent être placées hors semelle.
- Les textes techniques ne doivent pas se superposer au béton, aux aciers, aux cotations ou aux autres textes.
- Ajout d'une vue en plan schématique avec crochets d'ancrage à 135° pour les nappes inférieure et supérieure.
- Les crochets 135° sont représentés graphiquement et restent à vérifier selon EC2/BAEL et dispositions d'exécution.

## Version 0.27.0
- Ajout du plan final d'exécution fondations.
- Ajout endpoint :
  - POST /execution-foundation-dxf
- Le plan final regroupe :
  - emprise ;
  - axes et cotations ;
  - poteaux effectifs ;
  - fondations finales ;
  - ferraillage principal ;
  - attentes poteaux ;
  - tableau d'exécution ;
  - références aux détails ;
  - notes générales ;
  - cartouche.
- Le plan final référence les détails séparés :
  - coupes détaillées ;
  - ancrages / recouvrements ;
  - attentes poteaux ;
  - poinçonnement final.

## Version 0.27.0
- Ajout du plan final d'exécution fondations.
- Ajout endpoint :
  - POST /execution-foundation-dxf
- Le plan final regroupe :
  - emprise ;
  - axes et cotations ;
  - poteaux effectifs ;
  - fondations finales ;
  - ferraillage principal ;
  - attentes poteaux ;
  - tableau d'exécution ;
  - références aux détails ;
  - notes générales ;
  - cartouche.
- Le plan final référence les détails séparés :
  - coupes détaillées ;
  - ancrages / recouvrements ;
  - attentes poteaux ;
  - poinçonnement final.

## Version 0.27.1
- Correction du cartouche du plan final d'execution :
  - cases elargies ;
  - textes recadres ;
  - suppression des chevauchements.
- Ajout dans le meme dessin du plan final :
  - details ancrages ;
  - details attentes poteaux ;
  - sections types de ferraillage.
- Regle permanente :
  - le plan final d'execution doit integrer les renvois de details principaux ;
  - le cartouche doit etre lisible, cadre et sans chevauchement.

## Version 0.27.2
- Reprise complete des détails intégrés du plan final.
- Les détails d'ancrages, attentes et sections types sont agrandis et séparés.
- Les textes sont organisés en colonnes, hors des dessins techniques.
- Les cotes et notes ne doivent pas chevaucher les barres, semelles ou cadres.
- Le plan final ne doit pas compresser les détails au point de perdre la lisibilité.

## Version 0.28.0
- Ajout du métré estimatif fondations.
- Ajout endpoints :
  - POST /boq-foundations
  - POST /boq-foundations-csv
- Métré calculé :
  - béton fondations ;
  - béton de propreté ;
  - coffrage latéral ;
  - acier nappes inférieures et supérieures ;
  - acier attentes poteaux ;
  - poids acier total.
- Export CSV ajouté.
- Les quantités restent estimatives et doivent être vérifiées avec les plans d'exécution définitifs.

## Version 0.29.0
- Ajout de la note de calcul automatique.
- Ajout endpoints :
  - POST /calculation-report
  - POST /calculation-report-md
- La note regroupe :
  - hypothèses ;
  - stratégie fondations ;
  - ferraillage ;
  - poinçonnement final ;
  - ancrages ;
  - métré ;
  - réserves techniques.
- Export Markdown ajouté.
- La note reste une base de prédimensionnement et doit être validée par un ingénieur structure.

## Version 0.30.0
- Ajout de l'export DOCX de la note de calcul.
- Ajout de l'export PDF de la note de calcul.
- Ajout endpoints :
  - POST /calculation-report-docx
  - POST /calculation-report-pdf
- Les exports reprennent :
  - hypothèses ;
  - stratégie fondations ;
  - ferraillage ;
  - poinçonnement ;
  - ancrages ;
  - métré ;
  - réserves techniques.

## Version 0.32.0
- Ajout du contrôle qualité global du projet.
- Ajout endpoint :
  - POST /project-quality-check
- Vérifications :
  - fondations finales présentes ;
  - dimensions A/B/H valides ;
  - fondations dans l'emprise ;
  - contraintes sol cohérentes ;
  - tous les poteaux couverts ;
  - ferraillage présent ;
  - ferraillage final OK/WARNING/NOT_OK ;
  - poinçonnement final OK/WARNING/NOT_OK ;
  - ancrages présents ;
  - métré béton/acier cohérent.

## Version 0.32.0
- Ajout du contrôle qualité global du projet.
- Ajout endpoint :
  - POST /project-quality-check
- Vérifications :
  - fondations finales présentes ;
  - dimensions A/B/H valides ;
  - fondations dans l'emprise ;
  - contraintes sol cohérentes ;
  - tous les poteaux couverts ;
  - ferraillage présent ;
  - ferraillage final OK/WARNING/NOT_OK ;
  - poinçonnement final OK/WARNING/NOT_OK ;
  - ancrages présents ;
  - métré béton/acier cohérent.

## Version 0.32.2
- Correction conservative des warnings de poinçonnement.
- La correction ne s'applique plus seulement si utilisation > 1.00.
- Nouvelle règle :
  - si utilisation > 0.80, augmenter H.
- Objectif :
  - obtenir un contrôle qualité global sans erreur et idéalement sans warning de poinçonnement.

## Version 0.32.3
- Correction du warning global d'ancrage.
- Ajout d'une sécurisation constructive :
  - attentes poteaux avec crochet/crosse 135 degrés ;
  - statut ancrage : OK_WITH_EXECUTION_NOTES.
- Les longueurs Lbd/L0, rayons de cintrage et conditions d'adhérence restent à vérifier dans la note finale.
- Le contrôle qualité ne doit plus bloquer le dossier pour un ancrage sécurisé par disposition constructive explicite.

## Version 0.33.0
- Le ZIP final utilise maintenant la configuration corrigée issue de la remédiation qualité.
- Les livrables du dossier complet prennent en compte :
  - semelles recalées dans l'emprise ;
  - épaisseurs H augmentées pour poinçonnement ;
  - attentes sécurisées par crosses/crochets 135 degrés ;
  - contrôle qualité final OK.
- Le dossier ZIP ne doit plus être généré à partir de l'ancienne stratégie brute.

## Version 0.34.0
- Ajout du tableau de bord projet.
- Ajout endpoint :
  - POST /project-dashboard
- Le tableau de bord indique :
  - prêt à livrer : oui/non ;
  - statut qualité ;
  - statut ferraillage ;
  - statut poinçonnement ;
  - statut ancrages ;
  - résumé métré ;
  - corrections géométrie / poinçonnement / ancrages ;
  - liste des endpoints livrables.
- Le tableau de bord est basé sur la configuration corrigée.

## Version 0.35.0
- Ajout du rapport de synthèse projet.
- Ajout endpoints :
  - POST /project-summary-report-docx
  - POST /project-summary-report-pdf
- Le rapport de synthèse contient :
  - statut global prêt à livrer ;
  - statuts qualité / ferraillage / poinçonnement / ancrages ;
  - résumé des fondations ;
  - corrections appliquées ;
  - métré principal ;
  - liste des livrables ;
  - réserves d'ingénierie.

## Version 0.36.0
- Ajout du workflow IFC : Ifc -> API -> plan PDF + note de calcul.
- Ajout d'un lecteur IFC (civil_engine/readers/ifc_reader.py) qui produit le
  meme `model` que le lecteur DXF, afin de reutiliser tout le pipeline fondations.
- Conventions de mapping IFC :
  - IfcBuildingStorey tries par altitude ; le plus bas devient FONDATION,
    puis RDC, ETAGE1, ETAGE2... ;
  - IfcColumn rattaches a leur niveau et regroupes en piles verticales
    (poteaux P01, P02... partages, base portee au niveau FONDATION) ;
  - section des poteaux lue depuis le profil (rectangle / cercle), sinon
    section carree par defaut avec avertissement ;
  - IfcWall -> axes de voiles (representation Axis) au niveau FONDATION ;
  - emprise = rectangle englobant des elements structuraux + marge,
    dupliquee sur chaque niveau pour la descente de charges ;
  - toutes les coordonnees sont converties en metres via l'unite du projet IFC.
- Ajout du rendu PDF des plans DXF (civil_engine/plans/plan_pdf.py) via le
  backend matplotlib de ezdxf.
- Ajout endpoints :
  - POST /validate-ifc : resume du fichier IFC (niveaux, poteaux, voiles) ;
  - POST /extract-model-ifc : model.json depuis l'IFC ;
  - POST /ifc-workflow : ZIP contenant le plan d'execution en PDF (et son DXF),
    la note de calcul en PDF (et MD/DOCX), le model.json IFC et les JSON.
- Le workflow IFC s'appuie sur la configuration corrigee (remediation qualite :
  recalage dans l'emprise, augmentation de H pour le poinconnement, ancrages
  securises), conformement a la regle de la version 0.33.0.
- Le plan et la note restent un predimensionnement automatique a valider par un
  ingenieur structure. Le mapping IFC suppose des conventions de modelisation
  standard et doit etre verifie selon le modele BIM reel.
- Nouvelles dependances : ifcopenshell, matplotlib.

## Version 0.35.0
- Ajout du rapport de synthèse projet.
- Ajout endpoints :
  - POST /project-summary-report-docx
  - POST /project-summary-report-pdf
- Le rapport de synthèse contient :
  - statut global prêt à livrer ;
  - statuts qualité / ferraillage / poinçonnement / ancrages ;
  - résumé des fondations ;
  - corrections appliquées ;
  - métré principal ;
  - liste des livrables ;
  - réserves d'ingénierie.

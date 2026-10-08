# Boîtier « pot de fleur » Sentinel-X

Pot de fleur évasé, creux, qui s'ouvre en deux (charnière). Un bac à terre amovible ferme le haut ;
la caméra sort de la terre au centre, sur une tige entraînée par le servo, et tourne sur elle-même.
Modèle paramétrique OpenSCAD : `pot.scad` (toutes les cotes en tête de fichier).

| Pièce | Fichier | Contenu |
|---|---|---|
| Moitié avant | `stl/front.stl` | 2 trous du capteur à ultrasons, charnons, pattes de fermeture |
| Moitié arrière | `stl/back.stl` | Fenêtre de l'écran OLED, passage USB-C, platine du servo |
| Tige caméra | `stl/rod.stl` | Moyeu sur le palonnier, tige creuse (fils), tête qui loge l'ESP32-CAM |
| Bac à terre | `stl/tray.stl` | Fond plein, fourreau central pour la tige ; posé sur un rebord intérieur du pot |

Dimensions : pot Ø 188 mm (bandeau) × 140 mm ; la tête caméra dépasse de 48 mm au-dessus de la terre.
Chaque pièce tient sur un plateau d'impression de 220 × 220 mm.

## Impression

- PLA, buse 0,4, couches 0,2 mm, 3 périmètres, remplissage 15 %.
- Pièces imprimées dans le sens du modèle (fond sur le plateau).
- Supports : moitié arrière (platine du servo) et tige (dessous de la tête, plus large que la tige).

## Montage

1. **Charnière** : emboîter les deux moitiés et passer un bout de filament 1,75 mm dans les charnons.
2. **Fermeture** : 2 vis M3 × 16 + écrous dans les pattes, côté opposé à la charnière.
3. **Électronique** : UNO Q et breadboard au fond ; câble USB-C par le passage arrière.
4. **Capteur à ultrasons** : transducteurs dans les 2 trous de l'avant (colle chaude).
5. **Écran OLED** : derrière la fenêtre de l'arrière (colle chaude ou adhésif double face).
6. **Servo** : le glisser par le dessus dans la platine (pattes posées dessus), 2 vis M2.
7. **Caméra** : passer 2 fils 5V / GND dans la tige (ils ressortent par la fente en bas de la tige),
   les brancher sur l'ESP32-CAM (sans sa carte de programmation), glisser la carte par le dos ouvert
   de la tête, objectif contre la fenêtre, point de colle chaude.
8. **Tige** : mettre le servo à 90° (`POST /servo/90`), fixer le palonnier simple pointé vers l'avant,
   poser le moyeu dessus (branche du palonnier dans la rainure) ; vis du palonnier avec un tournevis
   fin passé par le trou du dessus de la tête et l'intérieur de la tige.
9. **Bac à terre** : l'enfiler sur la tige (fourreau central) et le poser sur le rebord intérieur.
   Le retirer avant d'ouvrir le pot.

## Ajuster aux composants

Mesurer et modifier en tête de `pot.scad`, puis réexporter :

| Variable | Défaut | Quoi |
|---|---|---|
| `us_d`, `us_spacing`, `us_z` | 16,6 / 26 / 55 mm | Diamètre, entraxe et hauteur des trous du capteur à ultrasons |
| `lcd_w`, `lcd_h`, `lcd_z` | 26 × 15 / 80 mm | Fenêtre de l'écran |
| `cam_w`, `cam_h`, `cam_d` | 28 × 41 × 22 mm | Logement de l'ESP32-CAM (profondeur : connecteurs dupont compris) |
| `lens_from_top`, `lens_win` | 10 / 12 mm | Position de l'objectif sur la carte, taille de la fenêtre |
| `Rb`, `R`, `H` | 70 / 90 / 140 mm | Rayons bas et haut, hauteur du pot |

Tête plus discrète : un module OV2640 à nappe longue (75 mm) permet de laisser la carte ESP32-CAM
dans la tige ou le pot et de ne garder qu'un petit cube d'environ 15 mm au-dessus de la terre.

```bash
openscad --backend=manifold -D 'PART="front"' -o stl/front.stl pot.scad   # front | back | rod | tray
openscad --backend=manifold -D 'PART="open"' pot.scad                       # aperçu sans la moitié avant
```

Aperçus : `preview/`.

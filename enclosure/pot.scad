// Sentinel-X : boîtier « pot de fleur » imprimable en 3D
//
//  - pot évasé avec bandeau en haut, creux, en 2 moitiés (avant / arrière) reliées par une charnière
//    imprimée (axe : un bout de filament 1,75 mm), fermé côté opposé par 2 vis M3
//  - bac à terre amovible, posé sur un rebord intérieur, avec un fourreau central
//  - servo SG90 au centre, sous la terre ; une tige creuse traverse le fourreau et porte la tête
//    caméra (ESP32-CAM) qui dépasse juste de la terre et tourne sur elle-même. Les fils passent
//    dans la tige
//  - avant : 2 trous pour les « yeux » du capteur à ultrasons ; arrière : fenêtre de l'écran OLED
//    et passage du câble USB-C
//
// Export d'une pièce : openscad -D 'PART="back"' -o back.stl pot.scad
PART = "all"; // all | open (sans la moitié avant) | front | back | rod | tray

$fn = 96;

// --- Pot (mm)
Rb = 70;         // rayon extérieur en bas
R = 90;          // rayon extérieur en haut
H = 140;         // hauteur
wall = 2.4;
floor_t = 3;
seam = 0.2;      // jeu entre les deux moitiés
band_h = 25;     // bandeau du haut
band_t = 4;      // surépaisseur du bandeau
function r_out(z) = Rb + (R - Rb) * z / H;
function r_in(z) = r_out(z) - wall;
taper = atan((R - Rb) / H);

// --- Charnière (côté gauche, -x, inclinée comme la paroi) et fermeture (côté droit, +x)
kn_r = 4;
kn_n = 5;
kn_gap = 0.5;
pin_d = 2.0;     // axe : filament 1,75 mm
kn_off = kn_r + 0.6;
hinge_z0 = 8;
hinge_z1 = H - band_h - 3;   // sous le bandeau
tab_len = 10;
m3 = 3.4;

// --- Bac à terre
tray_h = 25;
tray_top = H - 2;                 // la terre arrive juste sous le bord
ledge_z = tray_top - tray_h;      // rebord intérieur sur lequel repose le bac
tray_r = r_in(ledge_z) - 0.6;
tray_bottom = 3;

// --- Servo SG90 (axe au centre du pot)
sg_l = 23.0; sg_w = 12.6;
sg_shaft_off = 6.0;
sg_holes = 27.6;
plate_t = 4;
hub_t = 4;
hub_z = ledge_z - 3 - hub_t;      // dessous du moyeu de la tige (sur le palonnier)
plate_top = hub_z - 13;           // les pattes du servo reposent sur la platine

// --- Tige et tête caméra (ESP32-CAM seule, sans sa carte de programmation)
rod_d = 14;
rod_bore = 8;                     // passage des fils
sleeve_clear = 1.0;
head_z = tray_top + 3;            // dessous de la tête, juste au-dessus de la terre
cam_w = 28; cam_h = 41;           // carte
cam_d = 22;                       // carte + objectif + broches et connecteurs
head_wall = 2;
lens_from_top = 10;               // centre de l'objectif depuis le haut de la carte
lens_win = 12;

// --- Découpes
us_d = 16.6; us_spacing = 26; us_z = 55;   // capteur à ultrasons (avant)
lcd_w = 26; lcd_h = 15; lcd_z = 80;        // écran OLED 0,96" (arrière)
usb_w = 14; usb_h = 9; usb_z = 12;         // câble USB-C (arrière gauche)

echo(str("Pot Ø", 2 * (R + band_t), " x ", H, " mm ; tête caméra au-dessus de la terre : ",
         head_z + cam_h + 2 * head_wall - tray_top, " mm"));

// ---------------------------------------------------------------- pot
module shell() {
    difference() {
        union() {
            cylinder(h = H, r1 = Rb, r2 = R);
            translate([0, 0, H - band_h]) cylinder(h = band_h, r = R + band_t);
        }
        // intérieur, moins le rebord sur lequel repose le bac
        difference() {
            translate([0, 0, floor_t]) cylinder(h = H - floor_t + 1, r1 = r_in(floor_t), r2 = r_in(H + 1));
            translate([0, 0, ledge_z - 3]) difference() {
                cylinder(h = 3, r = r_in(ledge_z) + 2);
                translate([0, 0, -1]) cylinder(h = 5, r = r_in(ledge_z - 3) - 4);
            }
        }
        for (sx = [-1, 1])
            translate([sx * us_spacing / 2, r_in(us_z) - 5, us_z]) rotate([-90, 0, 0]) cylinder(h = wall + 10, d = us_d);
        translate([-lcd_w / 2, -r_out(lcd_z) - 5, lcd_z - lcd_h / 2]) cube([lcd_w, wall + 10, lcd_h]);
        rotate([0, 0, -120]) translate([r_in(usb_z) - 5, -usb_w / 2, usb_z - usb_h / 2]) cube([wall + 10, usb_w, usb_h]);
    }
}

module side_cut(front) {
    if (front) translate([-2 * R, seam, -1]) cube([4 * R, 2 * R, H + 2]);
    else translate([-2 * R, -2 * R, -1]) cube([4 * R, 2 * R - seam, H + 2]);
}

// Repère de la charnière : axe parallèle à la paroi (pot évasé), z local le long de l'axe.
module hinge_frame() {
    translate([-(Rb + kn_off), 0, 0]) rotate([0, -taper, 0]) children();
}

module knuckles(front) {
    s0 = hinge_z0 / cos(taper);
    s1 = hinge_z1 / cos(taper);
    seg = (s1 - s0) / kn_n;
    hinge_frame() for (k = [0 : kn_n - 1]) if ((k % 2 == 0) == front) {
        a = s0 + k * seg + (k == 0 ? 0 : kn_gap / 2);
        b = s0 + (k + 1) * seg - (k == kn_n - 1 ? 0 : kn_gap / 2);
        difference() {
            union() {
                translate([0, 0, a]) cylinder(h = b - a, r = kn_r);
                // liaison charnon / paroi, du seul côté de la moitié
                translate([0, front ? seam : -kn_r, a]) cube([kn_off * cos(taper) + wall - 0.4, kn_r - seam, b - a]);
            }
            translate([0, 0, -1]) cylinder(h = H * 2, d = pin_d);
        }
    }
}

module latch_tabs(front) {
    for (z = [18, hinge_z1 - 16])
        difference() {
            translate([r_in(z) - 1, front ? seam : -seam - 4, z]) cube([tab_len + wall + 1, 4, 14]);
            translate([r_out(z) + tab_len / 2, -10, z + 7]) rotate([-90, 0, 0]) cylinder(h = 20, d = m3);
        }
}

module servo_bridge() {
    intersection() {
        difference() {
            union() {
                translate([-16, -R, plate_top - plate_t]) cube([43, R + 16, plate_t]);
                translate([-2, -R, plate_top - plate_t - 10]) cube([4, R - 9, 10]);   // nervure
            }
            translate([-sg_shaft_off, -sg_w / 2, plate_top - plate_t - 1]) cube([sg_l, sg_w, plate_t + 2]);
            body_cx = -sg_shaft_off + sg_l / 2;
            for (sx = [-1, 1])
                translate([body_cx + sx * sg_holes / 2, 0, plate_top - plate_t - 1]) cylinder(h = plate_t + 2, d = 2);
        }
        translate([0, 0, plate_top - plate_t - 11]) cylinder(h = plate_t + 12, r = r_in(plate_top - plate_t - 11) - 0.5);
    }
}

module front_half() {
    intersection() { shell(); side_cut(true); }
    knuckles(true);
    latch_tabs(true);
}

module back_half() {
    intersection() { shell(); side_cut(false); }
    knuckles(false);
    latch_tabs(false);
    servo_bridge();
}

// ---------------------------------------------------------------- bac à terre
module tray() {
    sleeve_r = rod_d / 2 + sleeve_clear;
    difference() {
        union() {
            difference() {
                cylinder(h = tray_h, r = tray_r);
                translate([0, 0, tray_bottom]) cylinder(h = tray_h, r = tray_r - wall);
            }
            cylinder(h = tray_h, r = sleeve_r + 2);   // fourreau : la terre ne tombe pas dans le pot
        }
        translate([0, 0, -1]) cylinder(h = tray_h + 2, r = sleeve_r);
    }
}

// ---------------------------------------------------------------- tige + tête caméra
module head() {
    // Repère : z = 0 au dessous de la tête ; objectif vers +x. Dos ouvert : on glisse la carte,
    // objectif contre la fenêtre (point de colle chaude), fils vers la tige.
    hd = cam_d + 2 * head_wall;
    hw = cam_w + 2 * head_wall;
    hh = cam_h + 2 * head_wall;
    difference() {
        translate([-hd / 2, -hw / 2, 0]) cube([hd, hw, hh]);
        translate([-hd / 2 - 1, -cam_w / 2, head_wall]) cube([cam_d + head_wall + 1, cam_w, cam_h]);   // logement, dos ouvert
        translate([hd / 2 - head_wall - 1, -lens_win / 2, hh - head_wall - lens_from_top - lens_win / 2])
            cube([head_wall + 2, lens_win, lens_win]);                                                   // fenêtre objectif
        translate([0, 0, -1]) cylinder(h = head_wall + 2, d = rod_bore);                                 // vers la tige
        translate([0, 0, hh - head_wall - 1]) cylinder(h = head_wall + 2, d = 4);                        // tournevis (vis du palonnier)
    }
}

module rod() {
    // Repère : z = 0 au dessous du moyeu (posé sur le palonnier du servo).
    top = head_z - hub_z;
    difference() {
        union() {
            cylinder(h = hub_t, r = 11);
            cylinder(h = top, d = rod_d);
            translate([0, 0, top]) head();
        }
        translate([0, 0, hub_t]) cylinder(h = top, d = rod_bore);                                        // passage des fils
        translate([0, -rod_bore / 2, hub_t + 2]) cube([rod_d, rod_bore, 12]);                            // sortie des fils
        translate([0, 0, -1]) cylinder(h = hub_t + 2, d = 2.6);                                          // vis du palonnier
        translate([0, 0, -1]) cylinder(h = 3, d = 7.6);                                                  // moyeu du palonnier
        translate([0, -3.2, -1]) cube([18, 6.4, 3]);                                                     // branche du palonnier
    }
}

// ---------------------------------------------------------------- sortie
if (PART == "front") front_half();
else if (PART == "back") back_half();
else if (PART == "rod") rod();
else if (PART == "tray") tray();
else {
    if (PART != "open") color("#c8754a") front_half();
    color("#b5643d") back_half();
    color("#4a4a4a") translate([-sg_shaft_off, -sg_w / 2, plate_top - 16]) cube([sg_l, sg_w, 23]);   // servo (aperçu)
    color("#5b4636") translate([0, 0, ledge_z]) tray();
    color("#3d2b1f") translate([0, 0, ledge_z + tray_bottom]) difference() {                        // terre (aperçu)
        cylinder(h = tray_h - tray_bottom - 3, r = tray_r - wall);
        translate([0, 0, -1]) cylinder(h = tray_h, r = rod_d / 2 + sleeve_clear + 2);
    }
    color("#2a2a2a") translate([0, 0, hub_z]) rotate([0, 0, 90]) rod();                             // caméra vers l'avant
}

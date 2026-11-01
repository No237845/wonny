"""Génère les images de l'identité visuelle à partir du logo source.

Usage : python scripts/generer-images.py   (nécessite Pillow)

Source : config/identite/logo.jpg (fond blanc). Le fond extérieur au bouclier
devient transparent ; le blanc intérieur du bouclier est conservé.
"""

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

RACINE = Path(__file__).resolve().parent.parent
SOURCE = RACINE / "config/identite/logo.jpg"
ELEMENT = RACINE / "config/element/kibare"
KEYCLOAK = RACINE / "config/keycloak/themes/kibare/login/resources/img"
CONSOLE = RACINE / "admin-console/app/static"


def detourer(image: Image.Image) -> Image.Image:
    """Rend transparent le fond blanc relié aux bords (« couleur vers alpha » sur le liseré)."""
    rgb = image.convert("RGB")
    # Fond : pixels presque blancs reliés aux bords de l'image.
    clair = rgb.convert("L").point(lambda v: 255 if v > 232 else 0)
    fond = clair.copy()
    for coin in [(0, 0), (fond.width - 1, 0), (0, fond.height - 1), (fond.width - 1, fond.height - 1)]:
        ImageDraw.floodfill(fond, coin, 128)
    fond = fond.point(lambda v: 255 if v == 128 else 0)
    liseré = ImageChops.subtract(fond.filter(ImageFilter.MaxFilter(7)), fond)

    sortie = rgb.convert("RGBA")
    px, pf, pl = sortie.load(), fond.load(), liseré.load()
    for y in range(sortie.height):
        for x in range(sortie.width):
            if pf[x, y]:
                px[x, y] = (255, 255, 255, 0)
            elif pl[x, y]:
                r, g, b, _ = px[x, y]
                a = max(255 - r, 255 - g, 255 - b) / 255
                if a <= 0.01:
                    px[x, y] = (255, 255, 255, 0)
                else:
                    c = [round(min(255, max(0, (v - (1 - a) * 255) / a))) for v in (r, g, b)]
                    px[x, y] = (*c, round(a * 255))
    return sortie


def recadrer(image: Image.Image) -> Image.Image:
    """Recadre au plus près du bouclier, sans l'ombre portée du bas."""
    alpha = image.getchannel("A").point(lambda v: 255 if v > 40 else 0)
    gauche, haut, droite, bas = alpha.getbbox()
    # L'ombre est séparée du bouclier par des lignes vides : on coupe à la première.
    fin = haut
    while fin < bas and alpha.crop((0, fin, alpha.width, fin + 1)).getbbox():
        fin += 1
    marge = 6
    return image.crop((max(0, gauche - marge), max(0, haut - marge), min(image.width, droite + marge), fin + marge))


def carre(image: Image.Image, taille: int, marge: float, fond=None) -> Image.Image:
    toile = Image.new("RGBA", (taille, taille), fond or (255, 255, 255, 0))
    cote = round(taille * (1 - 2 * marge))
    logo = image.copy()
    logo.thumbnail((cote, cote), Image.LANCZOS)
    toile.alpha_composite(logo, ((taille - logo.width) // 2, (taille - logo.height) // 2))
    return toile


def main() -> None:
    logo = recadrer(detourer(Image.open(SOURCE)))
    for dossier in (ELEMENT, KEYCLOAK, CONSOLE):
        dossier.mkdir(parents=True, exist_ok=True)

    grand = logo.copy()
    grand.thumbnail((320, 320), Image.LANCZOS)
    grand.save(ELEMENT / "logo.png", optimize=True)
    grand.save(KEYCLOAK / "logo.png", optimize=True)
    petit = logo.copy()
    petit.thumbnail((96, 96), Image.LANCZOS)
    petit.save(CONSOLE / "logo.png", optimize=True)

    # Icône d'application (écran d'accueil, onglet) : fond blanc, marges.
    icone = carre(logo, 512, 0.1, (255, 255, 255, 255))
    icone.save(ELEMENT / "icone-512.png", optimize=True)
    icone.resize((192, 192), Image.LANCZOS).save(ELEMENT / "icone-192.png", optimize=True)
    favicon = carre(logo, 256, 0.02)
    for dossier in (ELEMENT, CONSOLE):
        favicon.save(dossier / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print("Images générées.")


if __name__ == "__main__":
    main()

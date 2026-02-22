# Braille Plus --- Handleiding

Welkom bij de handleiding voor de NVDA-add-on **Braille Plus**.\
Met Braille Plus kun je geselecteerde items markeren met punten 7 en 8
op de brailleleesregel.\
Daarnaast kan **opmaakinformatie** op de leesregel worden weergegeven
via **Attribra**.

------------------------------------------------------------------------

# Markeringen aanpassen via NVDA-instellingen

Je kunt de selectiemarkering in- of uitschakelen via:

**NVDA-menu → Opties → Instellingen → Braille**

Daar vind je de optie:

-   **"Markeer geselecteerde items met punten 7 en 8 (alleen
    itemtekst)"**

Schakel deze optie in of uit en klik op **OK** of **Toepassen** om de
wijziging op te slaan.

------------------------------------------------------------------------

# Sneltoets instellen via Invoerhandelingen

1.  Open **NVDA-menu → Opties → Invoerhandelingen**.
2.  Ga naar de categorie **Braille**.
3.  Zoek de actie:\
    **"Schakelt selectiemarkering met punten 7 en 8 in braille aan of
    uit."**
4.  Kies **Gebaar toevoegen**.
5.  Druk de gewenste sneltoets of voer het gewenste gebaar uit.
6.  Klik op **OK**.

------------------------------------------------------------------------

# Opmaak-informatie via Attribra

Wanneer een ingestelde regel overeenkomt met een documentattribuut
(bijvoorbeeld vetgedrukte tekst), voegt Attribra automatisch punten 7 en
8 toe aan de betreffende braillecellen.

------------------------------------------------------------------------

# Attribra-instellingen beheren via NVDA

Het is niet langer nodig om het bestand `attribra.ini` handmatig te
bewerken.\
Attribra heeft een eigen instellingenpaneel binnen NVDA.

## Attribra-instellingen openen

1.  Open het **NVDA-menu**.
2.  Ga naar **Opties → Instellingen**.
3.  Kies **Attribra** in de categorielijst.

------------------------------------------------------------------------

# Werken met toepassingen

Attribra werkt met toepassingen (secties):

-   **global** → regels gelden voor alle toepassingen.
-   Een specifieke toepassing (bijvoorbeeld `winword`) → regels gelden
    alleen binnen die toepassing.

## Een toepassing toevoegen

1.  Klik op **"Applicatie toevoegen..."**.
2.  Voer de naam van de toepassing in.
3.  Klik op **OK**.

## Een toepassing verwijderen

1.  Selecteer de applicatie.
2.  Klik op **"Applicatie verwijderen"**.
3.  Bevestig met **Ja**.

------------------------------------------------------------------------

# Regels beheren

Een regel heeft de vorm:

attribute = 0 of 1

Voorbeeld:

bold = 1

-   **1** → attribuut actief (punten 7 en 8 worden toegevoegd)
-   **0** → attribuut uitgeschakeld

## Een regel toevoegen

1.  Selecteer de juiste toepassing.
2.  Klik op **"Toevoegen..."**.
3.  Vul de attribuutnaam in.
4.  Kies de waarde (0 of 1).
5.  Klik op **OK**.

## Een regel bewerken

1.  Selecteer een regel.
2.  Klik op **"Bewerken..."**.
3.  Pas de gegevens aan.
4.  Klik op **OK**.

## Een regel verwijderen

1.  Selecteer de regel.
2.  Klik op **"Verwijderen"**.

------------------------------------------------------------------------

# Instellingen opslaan

Klik op **OK** of **Toepassen** om de wijzigingen op te slaan.\
De regels worden direct actief.

# Braille Plus --- Handleiding

Welkom bij de handleiding voor de NVDA-add-on **Braille Plus**.\
Met Braille Plus kun je geselecteerde items markeren met punten 7 en 8
op de brailleleesregel.\
Daarnaast kan **opmaakinformatie** op de leesregel worden weergegeven
via **Attribra**.

------------------------------------------------------------------------

## Markeringen aanpassen via NVDA-instellingen

Je kunt de selectiemarkering in- of uitschakelen via:

**NVDA-menu → Opties → Instellingen → Braille**

Daar vind je de optie:

-   **"Markeer geselecteerde items met punten 7 en 8 (alleen
    itemtekst)"**

Schakel deze optie in of uit en klik op **OK** of **Toepassen** om de
wijziging op te slaan.

------------------------------------------------------------------------

## Sneltoets instellen via Invoerhandelingen

Je kunt een sneltoets of braillegebaar instellen om de selectiemarkering
snel aan of uit te zetten:

1.  Open **NVDA-menu → Opties → Invoerhandelingen**.
2.  Ga naar de categorie **Braille**.
3.  Zoek de actie:
    -   **"Schakelt selectiemarkering met punten 7 en 8 in braille aan
        of uit."**
4.  Kies **Gebaar toevoegen**.
5.  Druk de gewenste sneltoets of voer het gewenste gebaar uit.
6.  Klik op **OK** om op te slaan.

------------------------------------------------------------------------

# Opmaak-informatie op de leesregel via Attribra

Naast selectiemarkering kan Braille Plus ook **opmaakinformatie** tonen
op de brailleleesregel.\
Dit gebeurt via **Attribra**.

Wanneer een ingestelde opmaakregel overeenkomt met een
documentattribuut, voegt Attribra automatisch punten 7 en 8 toe aan de
betreffende braillecellen.

------------------------------------------------------------------------

# Attribra-instellingen beheren

Attribra beschikt over een eigen instellingenpaneel binnen NVDA.
Handmatige bewerking van `attribra.ini` is niet meer nodig.

## Attribra-instellingen openen

1.  Open het **NVDA-menu**.
2.  Ga naar **Opties → Instellingen**.
3.  Kies in de categorielijst **Attribra**.

## Werking van het instellingenpaneel

### Sectie / Toepassing

Hiermee bepaal je voor welke toepassing de regels gelden:

-   **global** → regels gelden voor alle toepassingen\
-   Een specifieke programmanaam (bijvoorbeeld `winword`) → regels
    gelden alleen voor die toepassing

### Regels beheren

Een regel heeft de vorm:

attribuutnaam = 0 of 1

Voorbeeld:

bold = 1

-   **1** → attribuut is actief\
-   **0** → attribuut is uitgeschakeld

## Instellingen opslaan

Wanneer je op **OK** of **Toepassen** klikt, worden alle regels
opgeslagen en direct actief.

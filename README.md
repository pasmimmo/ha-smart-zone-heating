# Smart Zone Heating (Home Assistant Custom Integration)

Integrazione custom per Home Assistant pensata per gestire impianti di riscaldamento multi-zona (piani, zona giorno/notte, ecc.) con controllo generatore (stufa a pellet, caldaia, termocamino) e valvole di zona.

## Installazione via HACS (Archivio / Custom Repository)
1. Apri **HACS** in Home Assistant
2. Clicca sui 3 puntini in alto a destra $\rightarrow$ **Repository personalizzati**
3. Inserisci l'URL del repository Git e scegli categoria **Integrazione**
4. Installa **Smart Zone Heating** e riavvia Home Assistant.

## Test Locale con Docker
```powershell
docker compose up -d
```
Poi apri `http://localhost:8123`.

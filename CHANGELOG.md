# Changelog

All notable changes to this project will be documented in this file.

## [0.9.0] - 2026-10-26 (Pre-release)

### Added (EN)
- **Exclusive Control mode (`exclusive_control`)**: optional setting & configuration switch that strictly enforces physical switch states and automatically hides controlled switches (`heater_entity` and zone `valve_entity`) in the Home Assistant Entity Registry; when disabled (default), switches operate in edge-triggered mode so manual toggles are not immediately reverted.
- **Bidirectional Master Switch (`Impianto Abilitato`)**: toggling the master switch now sets all zone thermostats to `HVACMode.OFF` or `HVACMode.HEAT`, and automatically reflects `ON` whenever at least one zone thermostat is enabled.
- **Native Home Assistant Logbook & Context tracking**: every switch and thermostat command now attaches a linked `Context` and fires a descriptive `logbook_entry` event so the Home Assistant Activity panel clearly displays *what* and *why* caused each state change.
- Multi-zone thermostat creation (`climate`) with **Day**, **Night**, and **Away** preset modes.
- Automatic hourly Day / Night schedule transitions (`time` & `switch` entities) and Global Away mode switch.
- Dynamic temperature sensor selection per zone directly from the Device page (`select`).
- Smart Heat Dissipation (Cooldown) on heater shutdown: **Power sensor (Watts)** primary control with automatic **Timer fallback** if the power sensor is absent or becomes `unavailable`.
- Manual ignition safety valve control when power consumption exceeds threshold while idle.
- Diagnostic **Problem** binary sensor (`binary_sensor` with `device_class: problem`) for unavailable sensors or switches.
- Configurable notification service (`notify.*`) and verbosity level (`off`, `error`, `warning`, `debug`).
- Full Italian (`it`) and English (`en`) UI translations.

### Aggiunto (IT)
- **Modalità Controllo Esclusivo (`exclusive_control`)**: opzione nel wizard e switch di configurazione che, se attivo, blocca le modifiche manuali agli switch fisici e li nasconde automaticamente nella UI di Home Assistant; se disattivato (default), opera in modalità *edge-triggered* ignorando le modifiche manuali intermedie.
- **Interruttore Generale `Impianto Abilitato` sincronizzato coi Termostati**: spegnendo/accendendo lo switch generale tutti i termostati di zona passano a `OFF` / `HEAT` (mantenendo attive le sicurezze di smaltimento), con sincronizzazione bidirezionale se si accende/spegne un singolo termostato.
- **Integrazione nativa con il Registro Attività (Logbook & Context di Home Assistant)**: ogni cambio di stato comandato dall'integrazione propaga il `Context` e scrive nel Registro Attività la motivazione esatta dell'azione (richiesta calore, smaltimento Watt/Timer, sicurezza accensione manuale, Controllo Esclusivo, ecc.).
- Creazione termostati multi-zona (`climate`) con modalità **Giorno**, **Notte** e **Fuori Casa**.
- Cambio automatico per fascia oraria Giorno / Notte (`time` e `switch`) e interruttore generale Modalità Fuori Casa.
- Selezione dinamica del sensore di temperatura per ogni zona direttamente dalla pagina Dispositivo (`select`).
- Smaltimento calore intelligente allo spegnimento: controllo primario tramite **Sensore Watt** con **Timer di fallback** automatico in caso di indisponibilità del sensore.
- Apertura di sicurezza della valvola in caso di accensione manuale rilevata tramite assorbimento in Watt.
- Sensore binario diagnostico **Problema Impianto / Sensori** (`device_class: problem`) in caso di entità offline.
- Notificatore opzionale (`notify.*`) con livello di dettaglio regolabile (`off`, `error`, `warning`, `debug`).
- Traduzioni complete in Italiano (`it`) e Inglese (`en`).

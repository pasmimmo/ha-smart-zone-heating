# Changelog

All notable changes to this project will be documented in this file.

## [0.9.0] - 2026-10-26 (Pre-release)

### Added (EN)
- Multi-zone thermostat creation (`climate`) with **Day**, **Night**, and **Away** preset modes.
- Automatic hourly Day / Night schedule transitions (`time` & `switch` entities) and Global Away mode switch.
- Dynamic temperature sensor selection per zone directly from the Device page (`select`).
- Smart Heat Dissipation (Cooldown) on heater shutdown: **Power sensor (Watts)** primary control with automatic **Timer fallback** if the power sensor is absent or becomes `unavailable`.
- Manual ignition safety valve control when power consumption exceeds threshold while idle.
- Diagnostic **Problem** binary sensor (`binary_sensor` with `device_class: problem`) for unavailable sensors or switches.
- Configurable notification service (`notify.*`) and verbosity level (`off`, `error`, `warning`, `debug`).
- Full Italian (`it`) and English (`en`) UI translations.

### Aggiunto (IT)
- Creazione termostati multi-zona (`climate`) con modalità **Giorno**, **Notte** e **Fuori Casa**.
- Cambio automatico per fascia oraria Giorno / Notte (`time` e `switch`) e interruttore generale Modalità Fuori Casa.
- Selezione dinamica del sensore di temperatura per ogni zona direttamente dalla pagina Dispositivo (`select`).
- Smaltimento calore intelligente allo spegnimento: controllo primario tramite **Sensore Watt** con **Timer di fallback** automatico in caso di indisponibilità del sensore.
- Apertura di sicurezza della valvola in caso di accensione manuale rilevata tramite assorbimento in Watt.
- Sensore binario diagnostico **Problema Impianto / Sensori** (`device_class: problem`) in caso di entità offline.
- Notificatore opzionale (`notify.*`) con livello di dettaglio regolabile (`off`, `error`, `warning`, `debug`).
- Traduzioni complete in Italiano (`it`) e Inglese (`en`).

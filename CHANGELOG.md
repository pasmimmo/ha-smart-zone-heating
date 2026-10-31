# Changelog

All notable changes to **Smart Zone Heating** are documented in this file.

## [1.0.0] - 2026-10-31

### Added
- **Multi-Zone Native Thermostats (`climate`)**: Support for $1 \dots 10$ independent thermal zones with `Heat`/`Off` modes and `Day`, `Night`, and `Away` presets.
- **Smart Heat Dissipation (Watt-Driven Primary + Timer Fallback)**: Keeps a designated cooldown valve open after the heat generator turns off until power drops below the Watt threshold, with automatic timer fallback.
- **Manual Ignition Safety**: Automatically opens a safety zone valve when generator power exceeds the Watt threshold while thermostats are idle.
- **Exclusive Switch Control**: Option to hide managed physical switches in Home Assistant and immediately revert unauthorized manual state changes.
- **Rationalized Device Page UI**:
  - **Controlli (Controls)**: Ordered with Zone Thermostats first, followed by `Attiva Termostati`, `Fuori Casa`, and `Giorno/Notte` (with dynamic `Ora Giorno` / `Ora Notte` time entities appearing immediately below when enabled).
  - **Configurazione (Configuration)**: `Isteresi`, `Sensore <Zona>`, and `Notifiche` (with dynamic `Notifiche: Livello` appearing immediately below when enabled).
  - **Diagnostica (Diagnostics)**: Live status sensors for `Stato Sistema`, `Problema Sensori`, `Timer Smaltimento`, `Generatore`, `Consumo Generatore`, `Temperatura <Zona>`, and `Valvola <Zona>`.
- **Multi-Page Advanced Settings (`OptionsFlow`)**: Conditional step-by-step configuration via the integration gear icon with 1–2 line explanations under every field.
- **Unified Logbook & Debug Attribution**: Consistent `SZH Integration:` entries in Home Assistant's Activity Logbook and `[SZH Integration]` notifications across `Error`, `Warning`, and `Debug` levels.
- **Documentation**: Complete Italian (`doc/IT.md`) and English (`doc/EN.md`) manuals.

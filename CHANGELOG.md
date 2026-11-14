# Changelog

All notable changes to **Smart Zone Heating** are documented in this file.

## [1.1.1] - 2026-11-14

### Fixed
- **Immediate Persistence and In-Memory Application of `power_threshold_watt` in `OptionsFlow`**:
  - Added step-by-step persistence (`_persist_step_options`) across all `SmartZoneHeatingOptionsFlow` wizard steps (`async_step_init`, `async_step_cooldown`, `async_step_power_sensor`, `async_step_manual_safety`) so updated settings (such as `power_threshold_watt`) are saved immediately to `entry.data` and `entry.options` even if the dialog is closed before the final step.
  - Added `apply_options_in_place()` and `_load_advanced_settings()` on `SmartZoneHeatingCoordinator` to immediately apply new options in memory and re-evaluate manual ignition and cooldown thresholds, paired with `async_schedule_reload` on wizard completion.

## [1.1.0] - 2026-11-14

### Added
- **Generator Lifecycle Estimation (`generator_lifecycle.py`)**: Dedicated state machine estimating the real-time lifecycle phase of the heat generator (`OFF`, `STARTING`, `RUNNING`, `STOPPING_COOLDOWN`, `MANUAL_OVERRIDE`) via Watt power monitoring with automatic fallback to the safety cooldown timer.
- **Standardized `[SZH]` Entity Naming**: All entities created by the integration are now prefixed with `[SZH] <Entity Name>` (e.g., `[SZH] Generatore`, `[SZH] Termostato Piano 1`, `[SZH] Stato Sistema`) for immediate discovery and filtering in Home Assistant.
- **Structured Friendly-Name Notifications**: Notifications and Activity Logbook (`SZH`) now use entity `friendly_name` labels instead of raw `entity_id`s and format messages with clear `Status:`, `Reason:`, and `Value:` lines (`ℹ️[SZH] - <motivo>`).
- **Hydraulically Safe Actuation Ordering**: Guarantees that required zone valves open *before* turning on the heat generator (blocking generator startup if all demanding valves are `unavailable`) and that the heat generator turns off *before* closing zone valves.

### Changed
- **Modular Entity Architecture (`entity.py`)**: Consolidated common entity logic, device info, and Home Assistant `Context` propagation into `SmartZoneBaseEntity` and `SmartZoneEntity`.
- **Non-Destructive Dynamic Entity Visibility**: Dynamic configuration entities (`Ora Giorno`, `Ora Notte`, `Notifiche: Livello`) now use `RegistryEntryHider.INTEGRATION` instead of destructive entity registry removal.
- **Unified Documentation Structure**: Consolidated Italian and English manuals under `docs/IT.md` and `docs/EN.md`.

## [1.0.1] - 2026-11-01

### Added
- **Expressive System State (`Stato Sistema`)**: Displays active zone names directly in the status string (e.g., `Riscaldamento: Piano 1, Piano 2`, `Smaltimento: Piano 1 (85W)`, `Accensione manuale: Piano 1 (120W)`, `Problema: TP2 - Deumidificatore`, `Inattivo (Fuori Casa)`).
- **Startup Initialization Grace Period**: Suppresses false `Problema Sensori` / unavailability alerts during Home Assistant boot and for 30 seconds after startup so slower integrations (Wi-Fi, Zigbee) can finish initializing cleanly.

### Fixed
- **Logbook "What happened" (*Cosa è successo*) Causality**: Preserved exact Home Assistant `Context` ID across state writes, `logbook_entry` events, `Problema Sensori` transitions (`OK -> Problema` / `Problema -> OK`), and `switch.turn_on`/`turn_off` calls so the Activity Details dialog links the root cause (temperature sensor change, thermostat setpoint/mode change, unavailable sensor/switch, or manual switch toggle).
- **False Exclusive Control Reverts on Slow Wi-Fi Switches**: Added in-flight command tracking (`_pending_switch_cmd`) and clean recovery from `unavailable`/`unknown` states so slower Wi-Fi relays (e.g., Tapo plugs taking 2–4s to report state) do not trigger false `ripristino stato (controllo esclusivo)` commands when faster Zigbee relays update first.

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
- **Unified Logbook & Debug Attribution**: Consistent `SZH` entries in Home Assistant's Activity Logbook and `[SZH]` notifications across `Error`, `Warning`, and `Debug` levels.
- **Documentation**: Complete Italian (`docs/IT.md`) and English (`docs/EN.md`) manuals.

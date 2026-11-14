# Task Progress & Architectural Tracking (`develop` — v1.1.0)

## 🎯 Obiettivo Generale
Ottimizzazione, messa in sicurezza idraulica/asincrona, riorganizzazione della logica Watt in **"Stima ciclo vita generatore"**, standardizzazione nomi/notifiche `[SZH]`, suite di test containerizzata su **Home Assistant 2026.11.0** e riorganizzazione professionale della repository.

---

## ✅ Stato Avanzamento (100% Completato)
- [x] **Step 1 — Check Convenzioni, Best Practice e Fix Bug Critici**
- [x] **Step 2 — Infrastruttura di Test in Container Isolato (`.dev-tools/`) su Home Assistant 2026.11.0 (`16/16 passed`)**
- [x] **Step 3 — Riorganizzazione Logica in "Stima Ciclo Vita Generatore" (`generator_lifecycle.py`)**
- [x] **Step 4 — Refactoring del Codice, Organizzazione Moduli (`entity.py`) e Quality Gate (`ruff` + `py_compile` + `pytest`)**
- [x] **Step 5 — Standardizzazione Nomi Entità `[SZH]` e Formato Notifiche (`Status` / `Reason` / `Value`)**
- [x] **Step 6 — Organizzazione Professionale della Repository, Documentazione (`docs/`) e Release `1.1.0`**

---

## 📋 Dettaglio Operativo Completato

### 1. Sicurezza Idraulica, Resilienza e Convenzioni Home Assistant
- **Fix Reload Loop (`persist_config_option` & `OptionsFlow`):** Contatore `_ignore_update_listener_count` e `consume_internal_update_flag()` in `coordinator.py` e `__init__.py`.
- **Ordine Idraulico Garantito:** Apertura valvole *prima* dell'accensione del generatore (con blocco se nessuna valvola richiesta è disponibile) e spegnimento generatore *prima* della chiusura valvole.
- **Visibilità Dinamica Non Distruttiva:** Uso di `RegistryEntryHider.INTEGRATION` (`hidden_by`) al posto della rimozione dal registro entità.
- **Rilascio Controllo Esclusivo in Disinstallazione:** `async_release_all_managed_entities()` ripristina la visibilità di tutti gli switch gestiti quando l'integrazione viene rimossa.

### 2. Macchina a Stati "Stima Ciclo Vita Generatore" (`generator_lifecycle.py`)
- Sostituito `safety_manager.py` con `generator_lifecycle.py` (`CoordinatorGeneratorLifecycleMixin`).
- Fasi stimate (`GeneratorPhase` in `const.py`): `OFF` (`Spento`), `STARTING` (`In avvio`), `RUNNING` (`In funzione`), `STOPPING_COOLDOWN` (`Smaltimento calore`), `MANUAL_OVERRIDE` (`Acceso manualmente`).

### 3. Standardizzazione `[SZH]` e Notifiche (`notifier.py`)
- Prefisso `[SZH] <nome entità>` su tutte le entità create dall'integrazione (`climate`, `sensor`, `binary_sensor`, `number`, `switch`, `time`, `select`).
- `LOGBOOK_NAME = "SZH"` e `NOTIFY_PREFIX = "[SZH]"` in `models.py`.
- Notifiche strutturate su 3 righe (`Status:`, `Reason:`, `Value:`) utilizzando il `friendly_name` dell'entità.

### 4. Organizzazione Repository e Ambiente `.dev-tools/`
- Unificato tutto il tooling di sviluppo e test (automatico `test-runner` e live browser `ha-sandbox`) dentro `.dev-tools/`.
- Unificata la documentazione sotto `docs/` (`docs/IT.md`, `docs/EN.md`, `docs/assets/`).
- Aggiornati `manifest.json`, `README.md` e `CHANGELOG.md` alla versione `1.1.0`.

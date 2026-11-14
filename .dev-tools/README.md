# 🛠️ Smart Zone Heating — Ambiente di Sviluppo e Test (`.dev-tools/`)

> **Nota HACS:** Quando un utente installa **Smart Zone Heating** tramite HACS, viene scaricata sulla sua istanza Home Assistant **esclusivamente** la cartella [`custom_components/smart_zone_heating/`](../custom_components/smart_zone_heating). Tutto il contenuto di `.dev-tools/` resta unicamente nel repository GitHub per lo sviluppo e i test, senza mai finire sull'istanza dell'utente finale.

---

## 1. Eseguire i Test Automatici e i Controlli di Qualità (`pytest` + `ruff`)

Tutti i test automatici girano in un container isolato con **Python 3.14.10** e **Home Assistant 2026.11.0** (`pytest-homeassistant==2026.11.0` + `ruff==0.17.4`), senza sporcare il sistema operativo host:

```powershell
docker compose -f .dev-tools/docker-compose.test.yml run --rm test-runner
```

Il comando esegue in sequenza:
1. Verifica sintattica bytecode (`python3 -m py_compile custom_components/smart_zone_heating/*.py`).
2. Analisi statica e linting con **Ruff** (`ruff check --select E,F,W --ignore E501`).
3. **16 scenari di test end-to-end** (`pytest -c .dev-tools/pytest.ini .dev-tools/tests -v`):
   - `test_config_flow.py`: Wizard di prima configurazione e `OptionsFlow` multi-step.
   - `test_thermostat_and_hydraulics.py`: Isteresi Piano 1 / Piano 2, handover tra piani, priorità idraulica (*apri valvola $\rightarrow$ accendi generatore* e *spegni generatore $\rightarrow$ chiudi valvola*), blocco sicurezza su valvola `unavailable`.
   - `test_generator_lifecycle_and_safety.py`: Macchina a stati **Stima ciclo vita generatore** (`OFF` $\rightarrow$ `STARTING` $\rightarrow$ `RUNNING` $\rightarrow$ `STOPPING_COOLDOWN` $\rightarrow$ `OFF`), fallback a timer se il sensore Watt cade, accensione manuale (`MANUAL_OVERRIDE`).
   - `test_schedule_away_and_restore.py`: Ciclo Giorno/Notte, Fuori Casa, persistenza stati al riavvio (`RestoreEntity`), Controllo Esclusivo e formato notifiche `[SZH]`.

Per eseguire un singolo file o test specifico:
```powershell
docker compose -f .dev-tools/docker-compose.test.yml run --rm test-runner pytest -c .dev-tools/pytest.ini .dev-tools/tests/test_thermostat_and_hydraulics.py -v
```

---

## 2. Avviare l'Istanza Home Assistant Live per Test da Browser (`http://localhost:8123`)

Per provare manualmente l'integrazione da Chrome con dispositivi finti già pronti (3 switch + 2 sensori temperatura + 1 sensore Watt definiti in [`sandbox/config/configuration.yaml`](sandbox/config/configuration.yaml)):

```powershell
# Avvia Home Assistant 2026.11.0 in background su http://localhost:8123
docker compose -f .dev-tools/docker-compose.test.yml --profile sandbox up -d ha-sandbox
```

### Modificare il codice e ricaricare al volo
La cartella [`custom_components/smart_zone_heating`](../custom_components/smart_zone_heating) è montata direttamente dentro il container:
1. Modifica qualsiasi file Python in `custom_components/smart_zone_heating/`.
2. Riavvia il container per caricare le modifiche:
   ```powershell
   docker restart ha-smart-zone-test
   ```
3. Per fermare l'istanza live quando hai finito:
   ```powershell
   docker compose -f .dev-tools/docker-compose.test.yml --profile sandbox down
   ```
4. Per resettare completamente il database dell'istanza live (mantenendo solo `configuration.yaml`):
   ```powershell
   docker compose -f .dev-tools/docker-compose.test.yml --profile sandbox down
   Get-ChildItem -Path .dev-tools\sandbox\config -Force | Where-Object { $_.Name -ne "configuration.yaml" } | Remove-Item -Recurse -Force
   ```

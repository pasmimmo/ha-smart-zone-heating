# <img src="custom_components/smart_zone_heating/brand/icon.png" width="48" height="48" align="absmiddle" alt="Smart Zone Heating Icon" /> Smart Zone Heating for Home Assistant

[![HACS Validation](https://img.shields.io/github/actions/workflow/status/pasmimmo/ha-smart-zone-heating/validate.yml?label=HACS%20%26%20Hassfest)](https://github.com/pasmimmo/ha-smart-zone-heating/actions)
[![Version](https://img.shields.io/badge/version-0.9.0--pre-orange.svg)](https://github.com/pasmimmo/ha-smart-zone-heating/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-41BDF5.svg)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

🌍 **Language / Lingua:** [**🇮🇹 Italiano**](#-documentazione-in-italiano) | [**🇬🇧 English**](#-english-documentation)

---

# 🇮🇹 Documentazione in Italiano

**Smart Zone Heating** è un'integrazione custom per **Home Assistant** progettata per orchestrare impianti di riscaldamento multi-zona (es. *Zona Giorno / Zona Notte*, *Piano 1 / Piano 2*, o $N$ ambienti indipendenti) pilotando le relative **valvole di zona** e qualsiasi **Generatore di Calore** comandato da relè/contatto pulito (caldaie, termocamini, stufe idro, pompe di calore, ecc.).

---

## 💡 Perché questa integrazione? (Il mio caso d'uso)

Chiunque abbia provato a gestire in Home Assistant un impianto multi-zona con un generatore dotato di **inerzia termica** si scontra presto con un limite classico dei `generic_thermostat` standard:
* Se colleghi direttamente lo switch della valvola di zona al `generic_thermostat`, appena la stanza raggiunge la temperatura il termostato **chiude la valvola**, impedendo di tenerla aperta per smaltire il calore residuo del generatore in fase di arresto.
* Per aggirare il problema si finisce per costruire una catena fragile di `input_boolean` virtuali ("bottoni d'appoggio"), timer sparsi e automazioni incrociate difficili da mantenere.

### L'esempio pratico da cui è nato il progetto
Nel mio impianto domestico ho:
1. **Due zone termiche** (*Primo Piano* e *Secondo Piano*) comandate da **2 switch Zigbee** collegati alle valvole di zona.
2. **Un Generatore di Calore** (nel mio caso una stufa a pellet idro) pilotato da uno **switch a contatto pulito (dry-contact)** e collegato a una **presa smart che misura l'assorbimento in Watt**.
3. **Le regole fondamentali che volevo ottenere senza "spaghetti" di automazioni:**
   * Quando almeno un piano chiede calore $\rightarrow$ apre la valvola di quel piano e accende il generatore di calore.
   * Quando entrambi i piani sono arrivati in temperatura $\rightarrow$ spegne il generatore di calore, ma **mantiene aperta la valvola del Primo Piano per smaltire il calore residuo** della fase di spegnimento.
   * **Controllo intelligente tramite i Watt (con Timer di paracadute):** invece di affidarsi solo a un timer cieco di 1 ora, l'integrazione legge i Watt dalla presa smart e chiude la valvola di smaltimento non appena il consumo scende sotto i `10 W` (generatore realmente fermo e raffreddato), usando il timer di `60 minuti` come **fallback automatico** se la presa smart dovesse risultare offline.
   * **Sicurezza Accensione Manuale:** se qualcuno accende il generatore manualmente dal pannello fisico mentre i termostati di Home Assistant sono spenti, appena il consumo supera i `10 W` l'integrazione apre automaticamente la valvola del Primo Piano per evitare che il circolatore spinga a impianto chiuso.

**Smart Zone Heating** trasforma tutta questa logica in un componente universale, configurabile da interfaccia grafica in 2 minuti e raggruppato sotto **un unico Dispositivo nativo** di Home Assistant.

---

## 📊 Architettura e Logica di Funzionamento

### 1. Architettura Generale del Sistema
![Architettura del Sistema](docs/assets/architecture.svg)

### 2. Macchina a Stati: Riscaldamento, Smaltimento (Watt + Timer Fallback) e Sicurezza
![Macchina a Stati](docs/assets/state_machine.svg)

### 3. Priorità Apertura Valvole di Zona
![Logica Apertura Valvole](docs/assets/valve_logic.svg)

---

## ✨ Caratteristiche Principali (IT)

* **Multi-Zona Flessibile ($1 \dots 10$ zone):** Crea automaticamente un termostato nativo (`climate`) per ogni zona termica configurata.
* **3 Modalità (Preset) + Fasce Orarie Giorno/Notte:**
  * Ogni termostato supporta le modalità **Giorno (`day`)**, **Notte (`night`)** e **Fuori Casa (`away`)** con temperature indipendenti.
  * Cambio orario automatico tra **Giorno** e **Notte** agli orari impostati, più interruttore generale **Modalità Fuori Casa** per abbassare tutte le zone con un solo clic.
* **Selezione Dinamica dei Sensori:** Puoi cambiare al volo dalla pagina del Dispositivo quale sensore di temperatura della casa pilota ciascuna zona, senza riavviare Home Assistant.
* **Smaltimento Calore Intelligente (Watt Primario + Timer Fallback):**
  * Quando tutte le zone raggiungono la temperatura e il generatore di calore si spegne, l'integrazione mantiene aperta una **valvola di zona di dissipazione**.
  * **Controllo da Potenza (Primario):** Se è configurato un sensore di potenza (Watt), è l'assorbimento reale del generatore a decidere quando il ciclo di arresto è terminato: appena i Watt scendono sotto la soglia (es. $< 10\text{ W}$), la valvola viene chiusa.
  * **Timer di Emergenza (Fallback):** Se non hai il sensore dei Watt (o se diventa `unavailable`), entra in funzione automaticamente il timer configurabile (es. `60 min`).
* **Sicurezza Accensione Manuale (> Soglia W):**
  * Se il generatore di calore viene acceso manualmente dal comando fisico mentre i termostati sono spenti, non appena l'assorbimento elettrico supera la soglia (es. $\ge 10\text{ W}$) l'integrazione apre automaticamente la valvola di sicurezza designata.
* **Sensore Problema & Fail-Safe (`binary_sensor`):**
  * Monitora costantemente la disponibilità di tutti i sensori di temperatura, del sensore di potenza e degli switch (valvole e generatore).
  * Se un sensore di temperatura sparisce, interrompe per sicurezza la richiesta di calore di quella zona e attiva il sensore diagnostico **Problema Impianto / Sensori**.
* **Sistema di Notifiche Integrato (`Off` / `Error` / `Warning` / `Debug`):**
  * Invia notifiche opzionali sul cellulare (o notifiche persistenti su HA) filtrabili per livello di gravità.

---

## 🛠️ Installazione (IT)

### Metodo 1: Tramite HACS (Consigliato)
1. Apri **HACS** in Home Assistant.
2. Clicca sui 3 puntini in alto a destra $\rightarrow$ **Repository personalizzati** (*Custom repositories*).
3. Inserisci `https://github.com/pasmimmo/ha-smart-zone-heating` e seleziona la categoria **Integrazione** (*Integration*).
4. Clicca su **Scarica** su **Smart Zone Heating** (attiva *Mostra versioni beta / pre-release* se necessario per la `0.9.0`).
5. **Riavvia Home Assistant**.

### Metodo 2: Installazione Manuale
1. Scarica la cartella `custom_components/smart_zone_heating` da questo repository.
2. Copiala dentro `/config/custom_components/smart_zone_heating` della tua istanza Home Assistant.
3. **Riavvia Home Assistant**.

---

## 🧙‍♂️ Configurazione Guidata (Wizard UI)

Vai in **Impostazioni $\rightarrow$ Dispositivi e servizi $\rightarrow$ Aggiungi integrazione** e cerca **Smart Zone Heating**:

1. **Passo 1 – Zone e Orari Giorno/Notte:**
   * Scegli il nome dell'impianto, il **numero di zone termiche** ($1\dots10$) e gli orari per il cambio automatico **Giorno** (es. `07:00`) e **Notte** (es. `22:00`).
2. **Passo 2 – Configurazione Termostati di Zona (ripetuto per ogni zona):**
   * Imposta il nome della zona (es. *Zona Giorno*, *Zona Notte*, *Piano 1*), lo **Switch della valvola**, il **Sensore di temperatura** iniziale e le 3 temperature target (**Giorno**, **Notte**, **Fuori Casa**).
3. **Passo 3 – Switch Generatore di Calore, Sicurezza (Watt + Timer Fallback) e Notifiche:**
   * Seleziona lo **Switch del Generatore di Calore** (contatto pulito / relè).
   * Seleziona il **Sensore di potenza in Watt** (opzionale) e la **Soglia minima in Watt** (default `10 W`).
   * Imposta la **Durata del timer di fallback** (default `60 min`) e la **Valvola di zona da aprire per smaltimento / sicurezza**.
   * Di default la stessa valvola viene usata sia per lo smaltimento sia per l'accensione manuale; se attivi la spunta *"Usa un'altra valvola per l'accensione manuale"*, si aprirà il **Passo 4** per selezionare una seconda valvola dedicata.
   * Scegli il **Servizio di notifica** opzionale (es. `notify.mobile_app_...`) e il **Livello notifiche**.

---

## 📱 Entità Create nella Pagina Dispositivo

Tutte le entità si trovano raggruppate sotto **Impostazioni $\rightarrow$ Dispositivi e servizi $\rightarrow$ Smart Zone Heating $\rightarrow$ Dispositivo**:

| Sezione | Tipo Entità | Nome | Descrizione |
| :--- | :--- | :--- | :--- |
| **Controlli** | `climate` | `Termostato <Zona>` | Termostato nativo con modalità `Heat`/`Off` e preset **Giorno**, **Notte**, **Fuori Casa**. |
| **Controlli** | `switch` | `Impianto Abilitato` | Interruttore generale (Master Switch) per abilitare/disabilitare il riscaldamento. |
| **Controlli** | `switch` | `Modalità Fuori Casa` | Imposta tutte le zone in modalità *Fuori Casa* con un solo clic. |
| **Configurazione** | `select` | `Sensore Temperatura <Zona>` | Cambia al volo quale sensore di temperatura guida ciascuna zona. |
| **Configurazione** | `switch` | `Cambio Orario Giorno/Notte` | Abilita/disabilita il passaggio automatico tra *Giorno* e *Notte*. |
| **Configurazione** | `time` | `Orario Inizio Giorno` / `Notte` | Selettori orari per l'inizio della fascia Giorno e della fascia Notte. |
| **Configurazione** | `select` | `Valvola Smaltimento Calore` | Sceglie quale zona aprire durante lo smaltimento calore. |
| **Configurazione** | `select` | `Valvola Sicurezza Accensione Manuale` | Sceglie quale zona aprire se la potenza supera la soglia W a impianto spento. |
| **Configurazione** | `number` | `Soglia Consumo Sicurezza (W)` | Soglia in Watt sopra la quale il generatore è considerato attivo (default `10 W`). |
| **Configurazione** | `number` | `Durata Smaltimento Calore (min)` | Durata in minuti del timer di fallback per lo smaltimento (default `60 min`). |
| **Configurazione** | `number` | `Isteresi Termostati (°C)` | Tolleranza dei termostati di zona (default `0.3 °C`). |
| **Configurazione** | `select` | `Servizio di Notifica` / `Livello Notifiche` | Scelta del servizio `notify.*` e del livello (`Off`, `Error`, `Warning`, `Debug`). |
| **Diagnostica** | `binary_sensor` | `Problema Impianto / Sensori` | Si attiva (`Problema`) se un sensore o uno switch diventa `unavailable`, elencando negli attributi le entità offline. |
| **Diagnostica** | `sensor` | `Stato Sistema` | Mostra la fase corrente (*Inattivo*, *Riscaldamento*, *Smaltimento Watt/Timer*, *Sicurezza manuale*). |
| **Diagnostica** | `sensor` | `Minuti Residui Smaltimento` | Conto alla rovescia in minuti del timer di smaltimento. |

---
---

# 🇬🇧 English Documentation

**Smart Zone Heating** is a custom integration for **Home Assistant** designed to orchestrate multi-zone heating systems (e.g., *Day Zone / Night Zone*, *Floor 1 / Floor 2*, or $N$ independent rooms) by controlling **zone valves** and any relay/dry-contact **Heat Generator** (boilers, biomass/pellet hydro-stoves, wood thermo-stoves, heat pumps, etc.).

---

## 💡 Why This Integration? (Real-World Use Case)

Anyone who has tried to automate a multi-zone heating system in Home Assistant with a heat generator that has **thermal inertia** quickly runs into a major limitation of standard `generic_thermostat` entities:
* If you bind a zone valve switch directly to `generic_thermostat`, as soon as the room reaches target temperature the thermostat **closes the valve**—making it impossible to keep a zone valve open to dissipate residual heat while the generator is shutting down.
* Working around this in YAML usually requires a fragile web of virtual `input_boolean` helpers, timers, and cross-triggered automations.

### The Concrete Setup That Inspired This Project
In my home heating system, I have:
1. **Two thermal zones** (*First Floor* and *Second Floor*) controlled by **2 Zigbee switches** wired to the motorized zone valves.
2. **A Heat Generator** (a hydro pellet stove) controlled by a **dry-contact relay switch** and plugged into a **smart plug measuring real-time power in Watts**.
3. **The core rules I needed without automation spaghetti:**
   * When at least one zone calls for heat $\rightarrow$ open that zone's valve and turn on the heat generator switch.
   * When all zones are satisfied $\rightarrow$ turn off the heat generator switch, but **keep the First Floor valve open to dissipate residual heat** during the shutdown cycle.
   * **Smart Watt-Driven Cooldown (with Timer Fallback):** instead of relying solely on a blind 1-hour timer, the integration monitors the smart plug's Watts and closes the dissipation valve as soon as power drops below `10 W` (generator fully cooled down and stopped), while keeping a `60-minute` timer as an **automatic fallback** in case the smart plug goes offline.
   * **Manual Ignition Safety:** if someone turns on the heat generator manually from its physical button while Home Assistant thermostats are idle, as soon as power exceeds `10 W` the integration automatically opens the First Floor safety valve so the circulation pump never pushes against a closed circuit.

**Smart Zone Heating** packages this entire workflow into a generic, UI-configurable integration grouped under **a single native Home Assistant Device**.

---

## ✨ Key Features (EN)

* **Flexible Multi-Zone Control ($1 \dots 10$ zones):** Automatically creates a native `climate` thermostat entity for each configured thermal zone.
* **3 Preset Modes + Automatic Day/Night Schedule:**
  * Each thermostat supports **Day (`day`)**, **Night (`night`)**, and **Away (`away`)** presets with independent target temperatures.
  * Automatic hourly switching between **Day** and **Night** modes at configurable times, plus a global **Away Mode** switch to set all zones to Away with a single click.
* **On-the-fly Temperature Sensor Selection:** Change which room temperature sensor drives each zone directly from the Device page via a `select` dropdown, without restarting Home Assistant.
* **Smart Heat Dissipation / Cooldown (Power-Driven Primary + Timer Fallback):**
  * When all zones reach target temperature and the heat generator switch turns off, the integration keeps a designated **dissipation zone valve** open.
  * **Power Monitoring (Primary):** When a power sensor (Watts) is configured, real power consumption determines when the generator has finished its shutdown cycle: once power drops below the threshold (e.g., $< 10\text{ W}$), the dissipation valve closes immediately.
  * **Fallback Timer:** If no power sensor is configured—or if the power sensor becomes `unavailable`—the integration automatically falls back to a configurable cooldown timer (e.g., `60 min`).
* **Manual Ignition Safety (> Threshold W):**
  * If the heat generator is turned on manually from its physical control panel while all thermostats are idle, as soon as power consumption exceeds the safety threshold (e.g., $\ge 10\text{ W}$), the integration automatically opens the safety zone valve.
* **Problem Binary Sensor & Fail-Safe (`binary_sensor`):**
  * Continuously monitors availability of all temperature sensors, power sensor, and switches (zone valves and heat generator).
  * If a zone's temperature sensor becomes `unavailable`, that zone safely stops requesting heat and triggers the diagnostic **Problem** binary sensor (listing the offline entities in its attributes).
* **Built-in Notification System (`Off` / `Error` / `Warning` / `Debug`):**
  * Sends optional notifications to your phone (`notify.mobile_app_*` or any `notify.*` service) filtered by severity level.

---

## 🛠️ Installation (EN)

### Option 1: Via HACS (Recommended)
1. Open **HACS** in Home Assistant.
2. Click the three dots in the top-right corner $\rightarrow$ **Custom repositories**.
3. Paste `https://github.com/pasmimmo/ha-smart-zone-heating` and select the **Integration** category.
4. Click **Download** on **Smart Zone Heating**.
5. **Restart Home Assistant**.

### Option 2: Manual Installation
1. Download the `custom_components/smart_zone_heating` folder from this repository.
2. Copy it into `/config/custom_components/smart_zone_heating` in your Home Assistant configuration directory.
3. **Restart Home Assistant**.

---

## 🧪 Local Development & Testing with Docker

This repository includes a ready-to-use local Home Assistant test environment via Docker Compose:

```bash
docker compose up -d
```

Open `http://localhost:8123` in your browser. The test instance (`ha_test_config/configuration.yaml`) comes pre-configured with simulated switches and interactive sliders to test all states in real time.

---

## 🤝 Crediti / Credits

* **Ideazione, architettura impianto e casi d'uso reali:** [@pasmimmo](https://github.com/pasmimmo)
* **Sviluppo in Pair Programming, codice e diagrammi:** **Antigravity** *(Google DeepMind)*

---

## 📄 License

Distributed under the **MIT License**. See [LICENSE](LICENSE) for more information.


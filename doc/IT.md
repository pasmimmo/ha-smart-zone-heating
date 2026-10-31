# 🇮🇹 Smart Zone Heating — Manuale Completo (Italiano)

**[⬅️ Torna al README principale](../README.md)** | **[🇬🇧 Read in English](EN.md)**

---

## 📑 Indice

1. [Panoramica e Caso d'Uso Reale](#-1-panoramica-e-caso-duso-reale)
2. [Come Funziona la Logica Interna (Macchina a Stati)](#-2-come-funziona-la-logica-interna-macchina-a-stati)
3. [Installazione (HACS e Manuale)](#-3-installazione-hacs-e-manuale)
4. [Wizard di Prima Configurazione](#-4-wizard-di-prima-configurazione)
5. [Guida alla Pagina Dispositivo (Controlli, Configurazione, Diagnostica)](#-5-guida-alla-pagina-dispositivo-controlli-configurazione-diagnostica)
6. [Impostazioni Avanzate (Menu Ingranaggio `Configura`)](#-6-impostazioni-avanzate-menu-ingranaggio-configura)
7. [Controllo Esclusivo degli Switch](#-7-controllo-esclusivo-degli-switch)
8. [Registro Attività (Logbook) e Sistema di Notifiche](#-8-registro-attività-logbook-e-sistema-di-notifiche)

---

## 💡 1. Panoramica e Caso d'Uso Reale

**Smart Zone Heating** (`smart_zone_heating`) è un'integrazione custom per **Home Assistant** progettata per orchestrare impianti di riscaldamento multi-zona ($1 \dots 10$ zone o piani indipendenti) dotati di **elettrovalvole di zona** e di un **Generatore di Calore comune** comandato da relè / contatto pulito (stufe a pellet idro, termocamini, caldaie a biomassa o tradizionali, pompe di calore).

### Perché i normali termostati di Home Assistant non bastano?
Nei generatori con **inerzia termica** (come una stufa idro o una caldaia con ciclo di post-circolazione), quando tutte le stanze raggiungono la temperatura target e il contatto pulito spegne il generatore:
1. Il generatore non si arresta istantaneamente, ma impiega diversi minuti per spegnere la fiamma e raffreddare lo scambiatore.
2. Se tutte le valvole di zona si chiudessero subito al raggiungimento del target, la pompa di circolazione spingerebbe contro un circuito idraulico chiuso, mandando il generatore in **sovratemperatura / blocco di sicurezza**.
3. Allo stesso modo, se qualcuno accende il generatore **manualmente dal display fisico** mentre i termostati di Home Assistant sono spenti, serve un'automazione di sicurezza che se ne accorga (leggendo l'assorbimento in Watt) e apra immediatamente una valvola di sfogo.

**Smart Zone Heating** risolve nativamente tutto questo all'interno di **un unico Dispositivo di Home Assistant**, senza bisogno di `input_boolean` d'appoggio o catene di automazioni YAML.

---

## ⚙️ 2. Come Funziona la Logica Interna (Macchina a Stati)

![Architettura del Sistema](../docs/assets/architecture.svg)

L'integrazione valuta continuamente in tempo reale lo stato delle zone e del generatore secondo **4 fasi operative** (visibili nel sensore diagnostico **`Stato Sistema`**):

![Macchina a Stati](../docs/assets/state_machine.svg)

### Fase A — Riscaldamento in corso (`Riscaldamento in corso`)
* Ogni zona confronta la temperatura del proprio sensore con la temperatura target ($\pm$ **Isteresi**):
  * **Richiesta calore ON:** quando $T_{\text{attuale}} \le T_{\text{target}} - \text{Isteresi}$.
  * **Richiesta calore OFF:** quando $T_{\text{attuale}} \ge T_{\text{target}} + \text{Isteresi}$.
* Se **almeno una zona** richiede calore:
  * Vengono aperte le valvole delle sole zone in richiesta.
  * Viene acceso lo switch del **Generatore di Calore comune**.

### Fase B — Smaltimento Calore Residuo (`Smaltimento calore`)
* Non appena **tutte le zone** sono arrivate in temperatura (passaggio da *almeno una zona attiva* a *nessuna zona attiva*):
  1. Lo switch del **Generatore di Calore** viene spento (`OFF`).
  2. Se lo **Smaltimento Calore** è abilitato, l'integrazione forza l'apertura della **Valvola di smaltimento calore** designata (es. *Piano 1*) per dissipare il calore residuo dell'acqua.
  3. **Come decide quando chiudere la valvola di smaltimento?**
     * **Con Monitoraggio in Watt attivo (Primario):** attende i secondi di stabilizzazione iniziale (`power_grace_seconds`, default `15 s`) e mantiene aperta la valvola finché l'assorbimento elettrico del generatore è $\ge$ **Soglia funzionamento in Watt** (es. `10 W`). Appena il consumo scende sotto la soglia ($< 10\text{ W}$), il generatore ha terminato il ciclo di arresto e la valvola viene chiusa subito.
     * **Timer di Chiusura / Fallback:** se il monitoraggio in Watt non è attivo — oppure se la presa smart in Watt diventa `unavailable` durante lo smaltimento — la valvola resta aperta per il tempo impostato in **Temporizzazione chiusura (minuti)** (default `60 min`, monitorabile dal sensore **`Timer Smaltimento`**) e poi si chiude in sicurezza.

### Fase C — Sicurezza Accensione Manuale (`Sicurezza accensione manuale (> soglia W)`)
* Se i termostati non stanno chiedendo calore e l'impianto non è in fase di smaltimento, ma il sensore in Watt rileva un assorbimento $\ge$ **Soglia funzionamento in Watt** (es. qualcuno ha acceso la stufa a mano dal pannello fisico):
  * L'integrazione apre automaticamente la **Valvola di sicurezza accensione manuale** (che può essere la stessa dello smaltimento o una zona dedicata) e invia una notifica di **Warning**.
  * Quando i Watt tornano sotto la soglia, la valvola viene richiusa.

### Fase D — Protezione Guasti / Fail-Safe (`Attenzione: sensori indisponibili`)
* Se il sensore di temperatura di una zona diventa `unavailable` o `unknown`, quella zona interrompe per sicurezza la richiesta di calore, si accende il sensore binario **`Problema Sensori`** e viene inviata una notifica di **Error**.

---

## 🛠️ 3. Installazione (HACS e Manuale)

### Metodo 1: Tramite HACS (Consigliato)
1. Apri **HACS** in Home Assistant.
2. Clicca sui 3 puntini in alto a destra $\rightarrow$ **Repository personalizzati** (*Custom repositories*).
3. Inserisci `https://github.com/pasmimmo/ha-smart-zone-heating` e seleziona la categoria **Integrazione** (*Integration*).
4. Scarica **Smart Zone Heating** e **riavvia Home Assistant**.

### Metodo 2: Installazione Manuale
1. Copia la cartella `custom_components/smart_zone_heating` dentro `/config/custom_components/smart_zone_heating` della tua istanza Home Assistant.
2. **Riavvia Home Assistant**.

---

## 🧙‍♂️ 4. Wizard di Prima Configurazione

Vai in **Impostazioni $\rightarrow$ Dispositivi e servizi $\rightarrow$ Aggiungi integrazione** e cerca **Smart Zone Heating**:

1. **Passo 1 — Configurazione Termostati e Zone:**
   * **Nome dell'impianto** (es. *Riscaldamento Casa*).
   * **Numero di zone termiche** ($1 \dots 10$).
   * **Isteresi termostati (°C)** (default `0.3 °C`).
   * **Abilita ciclo orario Giorno / Notte** (se attivo, apre il **Passo 1b** per scegliere l'ora di inizio Giorno e l'ora di inizio Notte).
2. **Passo 2 — Termostato Zona $1 \dots N$ (ripetuto per ogni zona):**
   * **Nome della zona** (es. *Piano 1*, *Piano 2*, *Zona Giorno*).
   * **Switch valvola di zona** (`switch.*` che comanda l'elettrovalvola).
   * **Sensore di temperatura** (`sensor.*` che legge la temperatura della stanza).
   * **Temperature predefinite (°C)** per i 3 profili: **Giorno**, **Notte** e **Fuori Casa**.
3. **Passo 3 — Impostazioni Avanzate (Generatore, Smaltimento e Sicurezza):**
   * Segue lo stesso flusso guidato a pagine descritto nella [Sezione 6](#-6-impostazioni-avanzate-menu-ingranaggio-configura).

---

## 📱 5. Guida alla Pagina Dispositivo (Controlli, Configurazione, Diagnostica)

Aprendo **Impostazioni $\rightarrow$ Dispositivi e servizi $\rightarrow$ Smart Zone Heating**, trovi tutte le entità organizzate in **3 riquadri ordinati**:

### 🎛️ Riquadro `Controlli` (Uso Quotidiano)
Le voci sono ordinate esattamente per priorità d'uso:
1. **`Termostato <Zona>` (`climate`)** *(prime voci in alto)*
   * Termostato nativo di Home Assistant per ciascuna zona.
   * Modalità `Heat` (Attivo) / `Off` (Spento) e 3 profili selezionabili: **Giorno**, **Notte**, **Fuori Casa**.
2. **`Attiva Termostati` (`switch`)**
   * Interruttore generale sincronizzato bidirezionalmente con i termostati di zona: spegnendolo passa tutti i termostati in `Off`; accendendolo li riporta tutti in `Heat`. Se accendi anche un solo termostato manualmente, `Attiva Termostati` si porta su `ON`.
3. **`Fuori Casa` (`switch`)**
   * Attiva con un solo clic il profilo **Fuori Casa** su tutte le zone; spegnendolo riporta tutte le zone al profilo orario corrente (*Giorno* o *Notte*).
4. **`Giorno/Notte` (`switch`)**
   * Abilita o disabilita il cambio automatico di temperatura in base all'orario.
   * **Comportamento dinamico:** quando attivi **`Giorno/Notte`**, compaiono **immediatamente sotto** due selettori orari:
     * **`Giorno/Notte: Ora Giorno` (`time`)**
     * **`Giorno/Notte: Ora Notte` (`time`)**
     Quando spegni **`Giorno/Notte`**, i due selettori orari spariscono automaticamente per mantenere pulita l'interfaccia.

---

### 🔧 Riquadro `Configurazione` (Parametri Rapidi)
Contiene solo le regolazioni frequenti, nell'ordine:
1. **`Isteresi` (`number`)**
   * Tolleranza in `°C` (da `0.1 °C` a `2.0 °C`, default `0.3 °C`) prima di accendere o spegnere il riscaldamento.
2. **`Sensore <Zona>` (`select`)**
   * Menu a tendina per cambiare al volo quale sensore di temperatura della casa guida ciascuna zona, senza dover riconfigurare o riavviare l'integrazione.
3. **`Notifiche` (`select`)**
   * Seleziona il servizio `notify.*` su cui ricevere gli avvisi (es. `notify.mobile_app_...` o `notify.persistent_notification`, oppure `Disabilitate`).
   * **Comportamento dinamico:** quando selezioni un servizio diverso da `Disabilitate`, compare **immediatamente sotto** il selettore:
     * **`Notifiche: Livello` (`select`)**: permette di scegliere il livello di dettaglio (**Solo Errori**, **Warning + Errori**, **Tutti gli eventi / Debug**).

---

### 🩺 Riquadro `Diagnostica` (Stato a Colpo d'Occhio)
Mostra in tempo reale sia lo stato logico dell'integrazione sia **tutti i sensori e gli switch fisici selezionati**, così puoi controllarne il funzionamento in un'unica schermata (particolarmente utile quando il Controllo Esclusivo nasconde gli switch fisici dalla dashboard):

| Entità | Tipo | Cosa mostra a colpo d'occhio |
| :--- | :--- | :--- |
| **`Stato Sistema`** | `sensor` | Fase corrente: *Inattivo*, *Riscaldamento in corso*, *Smaltimento calore (controllo Watt)*, *Smaltimento calore (timer fallback)*, *Sicurezza accensione manuale*. |
| **`Problema Sensori`** | `binary_sensor` | `OK` se tutti i dispositivi rispondono; `Problema` se uno switch o sensore diventa `unavailable` (elencato negli attributi). |
| **`Timer Smaltimento`** | `sensor` | Minuti residui del timer di smaltimento calore *(visibile quando lo smaltimento calore è attivo)*. |
| **`Generatore`** | `sensor` | Stato live dello switch del generatore di calore selezionato (**`ON`** / **`OFF`** / **`Indisponibile`**) + entità sorgente negli attributi. |
| **`Consumo Generatore`** | `sensor` | Potenza live in **`W`** letta dal sensore di consumo selezionato *(visibile quando il monitoraggio in Watt è attivo)*. |
| **`Temperatura <Zona>`** | `sensor` | Temperatura live in **`°C`** letta dal sensore attualmente associato a ciascuna zona. |
| **`Valvola <Zona>`** | `sensor` | Stato live dello switch valvola di ciascuna zona (**`ON`** / **`OFF`** / **`Indisponibile`**) + eventuale motivo di apertura forzata negli attributi. |

---

## ⚙️ 6. Impostazioni Avanzate (Menu Ingranaggio `Configura`)

Cliccando sull'icona dell'**ingranaggio (`Configura`)** nella pagina del dispositivo si apre il flusso guidato **Impostazioni Avanzate**, organizzato a pagine condizionali con una spiegazione di 1-2 righe sotto ogni singola voce:

### 📄 Pagina 1 — `1. Generatore e Smaltimento`
* **Generatore di calore comune** (`heater_entity`): seleziona lo switch (contatto pulito / relè) che comanda il generatore di calore.
* **Controllo esclusivo degli switch** (`exclusive_control` Sì/No): se attivo, nasconde gli switch fisici in Home Assistant e annulla qualsiasi modifica manuale non conforme.
* **Gestisci smaltimento calore** (`cooldown_enabled` Sì/No): se attivo, mantiene aperta una valvola di zona dopo lo spegnimento del generatore per dissipare il calore residuo.
  * 👉 *Se metti **No**: il wizard salva e termina subito.*
  * 👉 *Se metti **Sì**: prosegue alla **Pagina 2**.*

### 📄 Pagina 2 *(se `Gestisci smaltimento calore` = Sì)* — `2. Smaltimento Calore`
* **Valvola di smaltimento calore** (`cooldown_zone_id`): quale valvola di zona mantenere aperta dopo lo spegnimento del generatore.
* **Usa dispositivo di monitoraggio Watt per capire lo stato di funzionamento** (`use_power_sensor` Sì/No): se attivo, usa un sensore in Watt per chiudere la valvola non appena il generatore si è arrestato.
* **Temporizzazione chiusura (minuti)** (`cooldown_minutes`): durata apertura valvola in minuti (se il monitoraggio Watt è attivo, questo timer viene usato automaticamente come paracadute/fallback se il sensore Watt non risponde).
  * 👉 *Se `Usa monitoraggio Watt` è **No**: non essendoci un sensore in Watt, il wizard salva e termina subito.*
  * 👉 *Se `Usa monitoraggio Watt` è **Sì**: prosegue alla **Pagina 2.1**.*

### 📄 Pagina 2.1 *(se `Usa monitoraggio Watt` = Sì)* — `2.1 Monitoraggio Watt`
* **Selettore sensore potenza (Watt)** (`power_sensor`): il sensore in Watt (es. presa smart) che misura il consumo del generatore.
* **Soglia funzionamento in Watt** (`power_threshold_watt`, default `10 W`): superiore a questa soglia l'impianto è considerato attivo; sotto questa soglia è considerato spento.
* **Attesa stabilizzazione lettura (secondi)** (`power_grace_seconds`, default `15 s`): secondi di attesa iniziale dopo lo spegnimento prima di verificare i Watt, per ignorare ritardi di aggiornamento del sensore.
  * 👉 *Prosegue alla **Pagina 3**.*

### 📄 Pagina 3 *(disponibile solo con Sensore Watt impostato)* — `3. Rilevamento Accensione Manuale`
* **Attiva rilevamento accensione manuale** (`manual_safety_enabled` Sì/No): se il consumo supera la soglia in Watt mentre i termostati sono spenti, apre automaticamente una valvola di sicurezza.
* **Usa una valvola diversa per l'accensione manuale** (`use_separate_manual_zone` Sì/No):
  * 👉 *Se **No**: usa la stessa valvola dello smaltimento calore, salva e chiude.*
  * 👉 *Se **Sì**: apre la **Pagina 3.1 (`Valvola Accensione Manuale`)** per scegliere la valvola dedicata, poi salva e chiude.*

---

## 🔒 7. Controllo Esclusivo degli Switch

L'opzione **Controllo esclusivo degli switch** (nelle *Impostazioni Avanzate*) definisce il rapporto tra l'integrazione e gli switch fisici (generatore + valvole di zona):

* **Quando è ATTIVO (`ON`):**
  1. Gli switch fisici gestiti vengono **nascosti automaticamente** (`hidden_by: integration`) dalle dashboard automatiche di Home Assistant per evitare tocchi accidentali. *(Il loro stato resta sempre visibile nel riquadro **Diagnostica** dell'integrazione).*
  2. Se uno switch fisico cambia stato manualmente in modo non conforme a quanto calcolato dall'integrazione, l'integrazione **lo riporta istantaneamente allo stato corretto** e registra nel Registro Attività:
     `SZH Integration: ripristino stato, <motivo> (controllo esclusivo)`.
* **Quando è DISATTIVO (`OFF`):**
  1. Gli switch fisici restano visibili normalmente in Home Assistant.
  2. L'integrazione opera in modalità *edge-triggered*: invia il comando `turn_on` / `turn_off` solo quando cambia lo stato richiesto dai termostati o dalle sicurezze, permettendoti di azionare manualmente uno switch tra un ciclo e l'altro senza essere sovrascritto all'istante.

---

## 📜 8. Registro Attività (Logbook) e Sistema di Notifiche

Ogni azione eseguita dall'integrazione utilizza un formato compatto e coerente sia nello **Storico / Registro Attività (Logbook)** di Home Assistant sia nelle **Notifiche**:

* **Nel Registro Attività (Logbook) dell'entità:**
  * `SZH Integration: -> on, Termostato Piano 1 18,5<22`
  * `SZH Integration: -> off, nessuna richiesta (22>=22)`
  * `SZH Integration: -> on, smaltimento calore (85W>=10W)`
  * `SZH Integration: ripristino stato, Termostato Piano 1 off (controllo esclusivo)`
* **Nelle Notifiche (`Error` / `Warning` / `Debug`):**
  * `[SZH Integration] switch.valvola_zona_piano_1 -> on, Termostato Piano 1 18,5<22`
  * `[SZH Integration] number.riscaldamento_casa_isteresi_termostati -> 0,5°C (precedente: 0,3°C)`
  * `[SZH Integration] input_number.potenza_stufa_watt accensione manuale rilevata (120W >= 10W) -> apertura sicurezza Piano 1`

# CertScope

[English](README.md)

CertScope è uno strumento locale per ispezionare certificati X.509 e verificare catene di fiducia. Accetta certificati PEM, catene PEM concatenate o singoli certificati DER. Mostra i dettagli dei certificati, verifica la fiducia e archivia certificati e CA con un nome personalizzato in SQLite.

## Requisiti e avvio

Python 3.14+, `uv`, Windows oppure Linux.

```bash
uv python install 3.14
uv sync
uv run certscope
```

Senza argomenti si apre la GUI. Incolla o carica il certificato/la chain nell'editor sinistro. Nell'editor destro puoi inserire una CA temporanea. Seleziona lo scopo della verifica e premi **Analyze and verify**. Dall'albero selezioni i certificati per visualizzare attributi e PEM originali. Le schede mostrano chain verificata, CA che ha autorizzato la validazione ed errori. **Saved entries** consente di caricare, rinominare, eliminare e gestire la fiducia dei certificati e delle CA memorizzati.

## CLI

```bash
uv run certscope inspect --cert server.pem --format json
uv run certscope verify --cert server-chain.pem
uv run certscope verify --cert server-chain.pem --ca private-root.pem
uv run certscope verify --cert server-chain.pem --purpose tls-server --hostname example.com
uv run certscope db add --type certificate --name Server --file server-chain.pem
uv run certscope db add --type ca --name RootAziendale --file root.pem --trust
uv run certscope db list
uv run certscope db trust --name RootAziendale --disable
uv run certscope --db ./local.sqlite3 verify --entry Server --format json
```

`-` legge da stdin (un solo argomento alla volta). `--leaf` consente di scegliere un certificato specifico tramite fingerprint SHA-256 se sono presenti più leaf. Codici di uscita: 0 successo, 1 verifica negativa, 2 input non valido, 3 errore operativo. L'opzione `--format json` produce risultati strutturati.

## Ordine di verifica

1. CA di sistema.
2. CA del database locale, esplicitamente attendibili e abilitate.
3. CA custom fornite temporaneamente dall'utente.

Ogni tentativo usa un archivio di fiducia indipendente. Appena una verifica riesce, le successive non vengono eseguite. La CA che completa la catena e i suoi attributi sono inclusi nel report. I certificati della chain inserita sono considerati candidati intermedi **non attendibili** finché non sono presenti tra le CA autorizzate. Salvare una CA non equivale ad autorizzarla.

`generic` verifica la catena X.509. `tls-server` controlla anche identità DNS/IP e scopo TLS, con hostname obbligatorio. `tls-client` controlla lo scopo di autenticazione client. La **revoca non viene verificata**, perché il programma opera offline senza scaricare OCSP/CRL/AIA. Su Windows la verifica OpenSSL delle CA esportate dallo store ROOT non riproduce tutte le policy di CryptoAPI, comprese alcune regole di esclusione. Il motore usa attualmente un adattatore pyOpenSSL isolato, le cui API crypto sono deprecate.

La GUI rifiuta chiavi private. Il limite iniziale è di 2 MiB e 100 certificati per input. Il database SQLite è nella directory dati dell'utente; la CLI supporta `--db` per cambiare percorso.

## Test e build Windows

```bash
uv run pytest -q
uv run ruff check .
```

Su Windows:

```powershell
uv sync --group dev
uv run pyinstaller --noconfirm --clean certscope.spec
.\dist\CertScope.exe --help
```

Il workflow GitHub Actions carica l'EXE come artifact. L'eseguibile mantiene la console per stdout, stderr e codici di ritorno della CLI; il doppio clic può aprire temporaneamente una console. PySide6/Qt e le altre dipendenze hanno licenze proprie da rispettare nella redistribuzione.

## Aspetto

Con **Settings** è possibile scegliere font monospaziato, dimensione (8–32 pt) e tema chiaro/scuro/automatico. Le preferenze restano nel database SQLite locale. Gli editor PEM e i risultati usano un componente Qt comune con evidenziazione; i dettagli strutturati hanno modalità **Tree** e **JSON**. Il font predefinito è JetBrains Mono Nerd Font Mono v3.5.1 (vedere `scripts/vendor-font.py` e la licenza inclusa).

La vista ad albero consente la selezione delle celle, Ctrl+C e il menu contestuale **Copy field / Copy value / Copy element**. Il testo copiato è completo anche quando il valore mostrato è abbreviato. La modalità Tree/JSON viene ripristinata dal database SQLite. Il tema chiaro rende leggibili i pulsanti e quello scuro utilizza righe alternate meno contrastate.

Il build Windows produce due EXE singoli: **CertScope.exe** avvia la GUI senza console; **CertScope-CLI.exe** conserva stdout, stderr e codici d'uscita per l'uso da terminale.

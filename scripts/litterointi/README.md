# Litterointi — nauhoitus + whisper (host)

Nauhoitus ja litterointi pyörivät **hostilla** (eivät kontissa): `rec`/`sox` äänen kaappaukseen ja whisper.cpp litterointiin. Skriptit kutsuvat hostin whisper-palvelinta (`:8178`) ja Ollamaa (tiedoston nimeämiseen).

```mermaid
sequenceDiagram
    autonumber
    actor U as Käyttäjä
    box rgb(227, 242, 253) Host-skriptit
        participant R as litterointi/record_and_transcribe.sh
        participant T as litterointi/transcribe_session.sh
        participant RF as litterointi/rename_file.py
    end
    box rgb(232, 245, 233) Host-palvelimet
        participant Rec as sox/rec
        participant W as whisper.cpp :8178
        participant O as Ollama
    end

    U->>R: recr
    R->>W: tarkista (GET /)
    loop Joka 2 min
        R->>Rec: rec → ${SESSIO}_NNN.wav
        Rec-->>R: wav-pätkä
        R->>W: POST /inference (wav)
        W-->>R: txt
    end
    U->>R: Ctrl+C
    Note over Rec: rec finalisoi keskeneräisen wavin
    R->>T: delegoi viimeistely
    T->>T: sox-combine backup-wav
    loop Puuttuville .txt:ille
        T->>W: POST /inference (wav)
        W-->>T: txt
    end
    T->>T: kokoa .md numerojärjestyksessä
    T->>RF: nimeä .md
    RF->>O: POST (MALLI_TEKSTIT, "anna lyhyt nimi")
    O-->>RF: nimi
    RF-->>T: renamed .md
    Note over T: istuntokansio poistuu vain onnistumisen jälkeen
```

## Ajaminen

```bash
# Nauhoitus (Ctrl+C lopettaa ja viimeistelee)
bash scripts/litterointi/record_and_transcribe.sh

# Viimeistele keskeytynyt istunto käsin (wavit tmp_chunks/$SESSIO/:ssä)
bash scripts/litterointi/transcribe_session.sh 2026-04-23_17-50-47

# Litteroi yksittäinen valmis wav
bash scripts/litterointi/transcribe_single_wav.sh /polku/tiedostoon.wav
```

## Skriptit

- `whisper_server.sh` — käynnistää whisper.cpp-palvelimen (`:8178`)
- `record_and_transcribe.sh` — 2 min wav-pätkät + live-litterointi taustalla
- `transcribe_session.sh` — istunnon viimeistely: backup-wav, puuttuvat litteroinnit, kokoaa `.md`:n, nimeää
- `transcribe_single_wav.sh` — yksittäinen valmis wav → `.txt`
- `rename_file.py` — AI-pohjainen `.md`:n uudelleennimeäminen (Ollama)

Host-binäärit: `/opt/homebrew/bin/{rec,sox}` ja `whisper-server` PATHissa. Skriptien väliset polut ratkaistaan `BASH_SOURCE`:n kautta, joten repo voi olla missä tahansa host-kansiossa.

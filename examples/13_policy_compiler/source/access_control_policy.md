# POL-SEC-042 — Politica di controllo degli accessi (rev. 4.2)

> Documento sorgente di esempio per il flusso "documento → Euclid-IR → KB".
> In un deployment reale questo testo arriverebbe da un sistema documentale
> (PDF/DOCX/Markdown). Qui è rappresentato in Markdown per leggibilità e per
> consentire al parser deterministico di suddividerlo in sezioni.
> La KB estratta si trova in `kb/access_control_policy.euclid`.

## 1. Oggetto e ambito di applicazione

La presente politica disciplina le modalità di accesso agli ambienti ICT e ai
dati aziendali per dipendenti e collaboratori. Essa si applica a tutti gli
utenti che dispongono di un account aziendale attivo. Un utente il cui account
non è attivo non ha diritto di accesso ad alcun ambiente.

## 2. Ambienti e livelli di sicurezza

Gli ambienti sono classificati in quattro fasce, con un livello minimo di ruolo
richiesto per il rilascio del software (deploy):

- **produzione**: livello minimo 6;
- **golden**: livello minimo 6;
- **staging**: livello minimo 4;
- **sviluppo (development)**: livello minimo 2.

## 3. Ruoli e gerarchia

Ogni ruolo ha un livello. I ruoli sono ordinati gerarchicamente e i permessi si
trasmettono per ereditarietà dal ruolo subordinato a quello sovraordinato. I
livelli assegnati ai ruoli sono: intern 0, junior_dev 1, mid_senior_dev 2,
senior_dev 3, tech_lead 4, eng_manager 5, director 6, vp_engineering 7,
cto 8.

## 4. Facoltà di rilascio

Un utente ha la facoltà di rilascio del software in un ambiente se dispone del
permesso di rilascio (deploy_code) e il livello del suo ruolo è maggiore o
uguale al livello minimo richiesto dall'ambiente. Solo gli utenti con account
attivo esercitano la facoltà.

## 5. Accesso ai dati classificati

I dati sono classificati in quattro livelli: public (1), internal (2),
confidential (3), secret (4). L'accesso a un dato richiede un livello di
abilitazione (clearance) dell'utente non inferiore al livello di
classificazione del dato.

## 6. Accesso in emergenza

In caso di incidente attivo, l'accesso in emergenza può essere concesso. La
concessione richiede l'approvazione di un utente autorizzato ad approvare; un
utente non può auto-approvare il proprio accesso in emergenza.

## 7. Deroghe

In casi eccezionali è possibile derogare al requisito di clearance. La deroga
richiede un'autorizzazione scritta ed è efficace solo se l'utente non è
sospeso.

## 8. Validità e revisione

La presente politica entra in vigore alla data di pubblicazione ed è rivista
con cadenza non superiore a dodici mesi.

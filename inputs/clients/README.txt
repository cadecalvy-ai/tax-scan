PUT REAL CLIENT FOLDERS HERE - one folder per client.

  inputs\clients\
    Smith_John\
      2025 Form 1040 (PDF), W-2s, 1099s, SSA-1099, K-1s, profile summary...
      client.yaml        <- required, see below
    Jones_Mary\
      ...

client.yaml must contain this one line, added only after the client's signed
IRC 7216 consent is on file:

  consent_7216: true

Without it the client is skipped (not graded).

Then double-click "Grade My Clients.bat" in the main Tax Scanner folder.
The ranking opens in your browser and is saved in outputs\clients_<date_time>\.

Privacy: everything in this folder stays on this computer. It is excluded from
GitHub and from the website. To try Tax Scan without real data, use
inputs\sample_clients (24 fictional clients).

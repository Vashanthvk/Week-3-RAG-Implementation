# Supply-chain risk note: contract-repository server (req #6)

Written and maintained by a different internal team; we did not review its source before wiring it in via `mcp_config.json`.
Reach today is narrow: it only reads its own local `contract_repository_data.json`, no network calls, no code shared with our own server.
It logs nothing -- no request/response trail, so misuse or compromise leaves no record to detect or investigate afterward.
Its three tools have no auth or per-caller scoping, so any caller (or a stolen token, once one exists) can enumerate every contract id, party, and amendment in the repository, including NDA'd ones.
Verdict: don't ship past this pilot until it logs calls, scopes access per-caller, and that team gives a straight answer on what the real production data source will actually contain.

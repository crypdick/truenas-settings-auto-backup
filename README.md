# truenas-settings-auto-backup
Script to automatically backup TrueNAS configs for Linux systems using the latest TrueNAS JSON-RPC 2.0 WebSocket API.

Inspired by https://git.pickysysadmin.ca/eric/truenas-config-backup, which does the same thing but uses PowerShell.

Notes:
- TrueNAS REST API is deprecated and being removed; this script uses the recommended WebSocket JSON-RPC API and the official client. See: [TrueNAS API Reference](https://www.truenas.com/docs/scale/api/) and [truenas/api_client](https://github.com/truenas/api_client).

## Usage

### Setup
- Optional: create a venv and install dependencies:
  
  ```bash
  python3 -m venv .venv
  . .venv/bin/activate
  pip install -r requirements.txt
  ```

### Provide API key
- Create a non-expiring API key in TrueNAS. Store it securely.
- Preferred: save it to a root-only file (example: `/root/.truenas_api_key`).
- Or export it as an environment variable `TRUENAS_API_KEY`.

### Run
- From the TrueNAS box itself (self-signed certs common):
  
  ```bash
  TRUENAS_API_KEY="$(cat /root/.truenas_api_key)" python3 backup.py \
    --host 127.0.0.1 \
    --out-dir /mnt/pool/backups/truenas \
    --include-secrets \
    --no-verify-tls
  ```

- From another Linux host with a valid certificate:
  
  ```bash
  export TRUENAS_API_KEY=your_api_key_here
  python3 backup.py \
    --host https://truenas.example.com \
    --out-dir /backups/truenas \
    --include-secrets
  ```

Notes:
- `--include-secrets` includes `secretseed` in the exported config.
- `--no-verify-tls` is useful for self-signed certs. Omit if you trust the CA.
- `--retention N` keeps the latest N backups (default 14).

## Run periodically on TrueNAS (Cron Job)

You can schedule this script directly on your TrueNAS system using a Cron Job.

### TrueNAS SCALE
- Open: System Settings → Advanced → Cron Jobs → Add
- Set:
  - User: root (or a service account with API access)
  - Schedule: as desired (e.g., Daily at 03:00)
  - Command (example):
    - If your API key is stored in a root-only file at `/root/.truenas_api_key`:
      
      ```bash
      TRUENAS_API_KEY="$(cat /root/.truenas_api_key)" /usr/bin/python3 /mnt/pool/scripts/truenas-settings-auto-backup/backup.py \
        --host 127.0.0.1 \
        --out-dir /mnt/pool/backups/truenas \
        --include-secrets
      ```
      

- Enable the job and click Run Now to test.

Notes (SCALE):
- Python path is typically `/usr/bin/python3`.
- Place the script in a dataset, e.g., `/mnt/pool/scripts/...`, and ensure execute permissions.

### TrueNAS CORE
- Open: Tasks → Cron Jobs → Add
- Set:
  - User: root (or a service account with API access)
  - Schedule: as desired
  - Command (example):
    
    ```bash
    TRUENAS_API_KEY="$(cat /root/.truenas_api_key)" /usr/local/bin/python3 /mnt/pool/scripts/truenas-settings-auto-backup/backup.py \
      --host 127.0.0.1 \
      --out-dir /mnt/pool/backups/truenas \
      --include-secrets
    ```
- Enable the job and click Run Now to test.

Notes (CORE):
- Python path is typically `/usr/local/bin/python3`.

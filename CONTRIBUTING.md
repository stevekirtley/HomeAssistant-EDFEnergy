## Development environment

### asdf

We use `asdf` to manage tool versions.

```bash
asdf plugin-add nodejs
asdf plugin-add python
sudo apt update && sudo apt upgrade
sudo apt install libffi-dev libncurses5-dev zlib1g zlib1g-dev libssl-dev libreadline-dev libbz2-dev libsqlite3-dev liblzma-dev
```

### Python dependencies

```bash
pip install -r requirements.test.txt
```

## Tests

### Unit tests

```bash
python -m pytest tests/unit
```

### Integration tests

Integration tests run against the live EDF Energy API. You need a valid refresh token and your meter details.

#### Getting a refresh token

Run the local test script and note the refresh token printed at the end:

```bash
python3 test_local.py
```

The script will print:
```
Refresh token to store: <your_refresh_token>
```

#### Running the tests

```bash
REFRESH_TOKEN=<refresh_token> \
ACCOUNT_ID=<account_id> \
ELECTRICITY_MPAN=<mpan> \
ELECTRICITY_SN=<serial_number> \
GAS_MPRN=<mprn> \
GAS_SN=<serial_number> \
python -m pytest tests/integration
```

#### GitHub Actions

The CI workflow runs integration tests using the following repository secrets:

| Secret | Description |
|---|---|
| `EDF_ENERGY_REFRESH_TOKEN` | A valid refresh token (obtained via `test_local.py`) |
| `EDF_ENERGY_ACCOUNT_ID` | Your account number (e.g. `A-AAAA1111`) |
| `EDF_ENERGY_ELECTRICITY_MPAN` | Your electricity MPAN |
| `EDF_ENERGY_ELECTRICITY_SN` | Your electricity meter serial number |
| `EDF_ENERGY_GAS_MPRN` | Your gas MPRN |
| `EDF_ENERGY_GAS_SN` | Your gas meter serial number |

Note: refresh tokens expire periodically. If integration tests start failing with authentication errors, re-run `test_local.py` to obtain a new token and update the secret.

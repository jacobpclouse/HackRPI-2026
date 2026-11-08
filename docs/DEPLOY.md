# Deploy DarkWatch on Databricks

The repo is a Databricks Asset Bundle. `databricks.yml` sits at the repo root and includes `databricks/resources/*.yml`.

| Thing | Name |
| --- | --- |
| Bundle target | `prod` (production mode, so names are not prefixed) |
| App | `darkwatch`, command `python backend/app.py` |
| Catalog / schema | `workspace.darkwatch` (bundle variables `catalog`, `schema`) |
| Job | `darkwatch_refresh`, every 6 hours, **paused** |
| SQL warehouse | bundle variable `warehouse_id`, no default |

Nothing workspace-specific is committed. The CLI takes the host from your profile (`databricks auth login`) or `DATABRICKS_HOST`. The bundle root path is `/Workspace/Users/${workspace.current_user.userName}/.bundle/darkwatch/prod`, so it resolves to whoever deploys.

## 1. Secret scope

Create only the keys the bundle references. A missing key fails the app deploy.

```bash
databricks secrets create-scope darkwatch
databricks secrets put-secret darkwatch fish_audio_api_key --string-value "$FISH_AUDIO_API_KEY"
databricks secrets put-secret darkwatch tiger_url --string-value "$TIGER_DATABASE_URL"
databricks secrets put-secret darkwatch aisstream_api_key --string-value "$AISSTREAM_API_KEY"
```

`aisstream_api_key` is referenced by the app resource. Create it before deploy or the app will fail to start on Databricks. Locally the same value is `AISSTREAM_API_KEY` in `.env`; background refresh also needs `AIS_GLOBAL_REFRESH=1`.

`tiger_url` is a Postgres URL (`postgresql://...` or `postgres://...`). The refresh job reads it with `dbutils.secrets.get` and writes hypertables. The app reads it as `TIGER_DATABASE_URL`. If the URL is set but the database is down, the app falls through to the SQL warehouse and then to the bundled demo.

You need **MANAGE** on the scope to create it and to let the app's service principal be granted **READ**.

### Optional keys (not in the bundle)

Do **not** add these to `app.yaml` or `databricks/resources/darkwatch.app.yml` until the secrets exist. Referencing a missing key breaks deploy.

| Scope `darkwatch` key | Env var the app already understands | What it does |
| --- | --- | --- |
| `gemini_api_key` | `GEMINI_API_KEY` | Rewrites candidate briefs. Without it, a local template is used. |
| `gfw_api_token` | `GFW_API_TOKEN` | Compares detections with Global Fishing Watch. Without it, the endpoint says the token is unset. |

After you create one, add a resource and a `value_from` entry (snake_case; the CLI ignores `valueFrom`):

```yaml
- name: gemini-key
  secret:
    scope: darkwatch
    key: gemini_api_key
    permission: READ
```

```yaml
- name: GEMINI_API_KEY
  value_from: gemini-key
```

Put the resource under `resources:` in `databricks/resources/darkwatch.app.yml` and the env entry in both that file and `app.yaml`.

`FISH_AUDIO_VOICE_ID` is not a secret. It defaults to Aria, `933563129e564b19a115bedd57b7406a`, a public English female voice from the Fish Audio library (see `.env.example`). The model header defaults to `s2.1-pro-free`. Both defaults live in `backend/darkwatch/config.py`; add an env entry to override.

## 2. Validate and deploy

From the repo root, with your warehouse id:

```bash
export BUNDLE_VAR_warehouse_id=<your-serverless-warehouse-id>
databricks bundle validate -t prod
databricks bundle deploy -t prod
databricks bundle run darkwatch -t prod
```

`bundle deploy` uploads the project (minus `data/raw`, `data/cache`, `.venv`, and the tests, see `sync.exclude`) and creates the app, schema, and job, and leaves the app stopped. `bundle run darkwatch` applies the app config and starts it. The app listens on `0.0.0.0:$DATABRICKS_APP_PORT`.

Databricks Apps installs `requirements.txt` from the app root. That file is a one-line pointer to `backend/requirements.txt`, which takes its versions from `backend/constraints.txt`.

Open the URL from:

```bash
databricks apps get darkwatch
```

The service principal is granted `CAN_USE` on the warehouse and `READ` on scope `darkwatch` because those resources are declared on the app.

## 3. Let the app read Delta tables

Tables do not exist until the refresh job succeeds. After that, grant the app service principal (shown on the app's Authorization page) select on the schema:

```sql
GRANT USE CATALOG ON CATALOG workspace TO `<app-service-principal>`;
GRANT USE SCHEMA ON SCHEMA workspace.darkwatch TO `<app-service-principal>`;
GRANT SELECT ON SCHEMA workspace.darkwatch TO `<app-service-principal>`;
```

Until those grants exist, or before the first job run, the app serves the bundled Kattegat demo in `data/demo` (no warehouse required).

Read order at runtime:

1. Tiger, if `TIGER_DATABASE_URL` is injected and `scenes` has a row.
2. SQL warehouse `workspace.darkwatch`, using the app service principal (`DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`) and `databricks-sql-connector`.
3. Bundled demo files.

`/api/health` reports `data.source` as `tiger`, `warehouse`, or `bundle`, and lists anything running on a fallback under `fallbacks`.

## 4. Run the refresh job

The schedule is `0 0 */6 * * ?` UTC and **paused**. Run it once by hand:

```bash
databricks bundle run darkwatch_refresh -t prod
```

Unpause later with a job edit, or set `pause_status: UNPAUSED` in `databricks/resources/darkwatch_refresh.job.yml` and deploy again.

The job is a serverless `spark_python_task` on environment version **4** (Python 3.12) running `backend/jobs/refresh.py`. It does not use `__file__`. It finds the repo from `sys.argv[0]`, the working directory, and `--repo-root ${workspace.file_path}` by looking for the `.darkwatch-root` marker.

Its `dependencies` list must equal `backend/constraints.txt` for every package in `backend/requirements-job.txt`. `backend/tests/test_pins.py` fails if they drift.

Each run:

- pulls current CelesTrak GP elements for the SAR missions
- searches Planetary Computer for the newest Sentinel-1 RTC scene over the Kattegat chip whose calendar day has `aisdk-YYYY-MM-DD.zip` on the public Danish AIS bucket
- runs CA-CFAR and AIS matching
- writes `scenes`, `detections`, `ais_pings`, `matches`, and `passes` in `workspace.darkwatch`
- if `tiger_url` can be read, also writes those tables in Tiger (`ais_pings` and `passes` as hypertables)

Egress the job needs: `celestrak.org`, `planetarycomputer.microsoft.com`, `*.blob.core.windows.net`, `aisdata.ais.dk.s3.eu-central-1.amazonaws.com`, `naciscdn.org`.

Rasterio is a job dependency (manylinux wheel, no apt). It is not in `backend/requirements.txt`, so the app image does not need GDAL.

## 5. Local equivalent

```bash
make test        # creates .venv with app + job + dev dependencies
make check-job   # python backend/jobs/refresh.py --check
make dev         # python backend/app.py on :8741
```

`python backend/app.py` is the same command the app runs. Without Databricks env vars it serves the bundled scene.

## Files

| File | Role |
| --- | --- |
| `databricks.yml` | Bundle root: variables, `sync.exclude`, the `prod` target |
| `databricks/resources/darkwatch.app.yml` | App, SQL warehouse, two secrets, command and env |
| `databricks/resources/darkwatch.schema.yml` | `workspace.darkwatch` |
| `databricks/resources/darkwatch_refresh.job.yml` | Paused 6-hour serverless job |
| `app.yaml` | Same command and env for `databricks apps deploy` without the bundle |
| `requirements.txt` | Pointer to `backend/requirements.txt` for the Apps installer |
| `backend/app.py` | Binds `0.0.0.0` and `$DATABRICKS_APP_PORT` (else `$PORT`, else 8741) |
| `backend/jobs/refresh.py` | Refresh script |
| `backend/constraints.txt` | Every version pin |
| `backend/requirements.txt` | App image only (no rasterio) |
| `backend/requirements-job.txt` | Job / `make prepare` dependencies |

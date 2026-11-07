# Databricks notebook source
# MAGIC %md
# MAGIC # DarkWatch — AIS and SAR detection join
# MAGIC
# MAGIC Hackathon track notebook. It is not part of `make dev`.
# MAGIC Point the widgets at Delta tables that mirror the demo schema, then run
# MAGIC the same match the FastAPI service does in Python: interpolate AIS to the
# MAGIC Sentinel-1 acquisition time and flag detections with no public AIS inside
# MAGIC 3 km.
# MAGIC
# MAGIC Unmatched means not matched to public AIS. It is not evidence of wrongdoing.

# COMMAND ----------

dbutils.widgets.text("ais_table", "darkwatch.ais_pings", "AIS Delta table")
dbutils.widgets.text("detection_table", "darkwatch.detections", "Detection Delta table")
dbutils.widgets.text("scene_time", "2026-11-02T05:23:46Z", "Acquisition time (UTC)")
dbutils.widgets.text("max_km", "3.0", "Match radius km")
dbutils.widgets.text("max_gap_minutes", "10", "Max AIS bracket")

# COMMAND ----------

ais_table = dbutils.widgets.get("ais_table")
det_table = dbutils.widgets.get("detection_table")
scene_time = dbutils.widgets.get("scene_time")
max_km = float(dbutils.widgets.get("max_km"))
max_gap = int(dbutils.widgets.get("max_gap_minutes"))

spark.sql(f"""
CREATE OR REPLACE TEMP VIEW ais_at_scene AS
WITH ordered AS (
  SELECT
    mmsi,
    name,
    lat,
    lon,
    ts,
    lead(ts) OVER (PARTITION BY mmsi ORDER BY ts) AS next_ts,
    lead(lat) OVER (PARTITION BY mmsi ORDER BY ts) AS next_lat,
    lead(lon) OVER (PARTITION BY mmsi ORDER BY ts) AS next_lon
  FROM {ais_table}
)
SELECT
  mmsi,
  name,
  lat + (unix_timestamp(timestamp('{scene_time}')) - unix_timestamp(ts))
        / (unix_timestamp(next_ts) - unix_timestamp(ts)) * (next_lat - lat) AS lat,
  lon + (unix_timestamp(timestamp('{scene_time}')) - unix_timestamp(ts))
        / (unix_timestamp(next_ts) - unix_timestamp(ts)) * (next_lon - lon) AS lon
FROM ordered
WHERE ts <= timestamp('{scene_time}')
  AND next_ts > timestamp('{scene_time}')
  AND (unix_timestamp(next_ts) - unix_timestamp(ts)) BETWEEN 1 AND {max_gap} * 60
""")

# COMMAND ----------

# MAGIC %md
# MAGIC Haversine in kilometres. One-to-one assignment is left to a later rank filter
# MAGIC so two detections cannot claim the same MMSI.

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TEMP VIEW detection_ais AS
SELECT
  d.det_id,
  d.lat AS det_lat,
  d.lon AS det_lon,
  d.peak_db,
  a.mmsi,
  a.name,
  2 * 6371 * asin(sqrt(
      pow(sin(radians(a.lat - d.lat) / 2), 2)
      + cos(radians(d.lat)) * cos(radians(a.lat)) * pow(sin(radians(a.lon - d.lon) / 2), 2)
  )) AS dist_km
FROM {det_table} d
LEFT JOIN ais_at_scene a
  ON abs(a.lat - d.lat) < 0.05 AND abs(a.lon - d.lon) < 0.08
""")

spark.sql(f"""
CREATE OR REPLACE TEMP VIEW matched AS
SELECT * FROM (
  SELECT
    *,
    row_number() OVER (PARTITION BY det_id ORDER BY dist_km) AS det_rank,
    row_number() OVER (PARTITION BY mmsi ORDER BY dist_km) AS mmsi_rank
  FROM detection_ais
  WHERE dist_km IS NULL OR dist_km <= {max_km}
)
WHERE (mmsi IS NULL) OR (det_rank = 1 AND mmsi_rank = 1)
""")

# COMMAND ----------

summary = spark.sql("""
SELECT
  count(*) AS detections,
  count(mmsi) AS matched_to_public_ais,
  count(*) - count(mmsi) AS unmatched_potential_dark_vessels
FROM matched
""")
display(summary)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Who was still reporting during a coverage gap
# MAGIC
# MAGIC Replace the timestamps with a gap computed by the DarkWatch orbit service
# MAGIC (`/api/coverage`). Do not hardcode a duration.

# COMMAND ----------

dbutils.widgets.text("gap_start", "2026-11-02T08:00:00Z", "Gap start")
dbutils.widgets.text("gap_end", "2026-11-02T14:00:00Z", "Gap end")
gap_start = dbutils.widgets.get("gap_start")
gap_end = dbutils.widgets.get("gap_end")

display(spark.sql(f"""
SELECT mmsi, max(name) AS name, count(*) AS pings, min(ts) AS first_ping, max(ts) AS last_ping
FROM {ais_table}
WHERE ts >= timestamp('{gap_start}') AND ts < timestamp('{gap_end}')
GROUP BY mmsi
ORDER BY pings DESC
LIMIT 50
"""))

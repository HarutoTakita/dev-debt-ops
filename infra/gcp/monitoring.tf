# Observability. Cloud Run stdout/stderr is auto-ingested into Cloud Logging (no log sink
# needed — the GCP equivalent of azure's Log Analytics wiring is built in). We add a
# log-based 5xx metric + alert, and an uptime check (gated on a domain being set).
resource "google_logging_metric" "api_5xx" {
  name   = "${local.name_prefix}-api-5xx"
  filter = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${google_cloud_run_v2_service.api.name}\" AND httpRequest.status>=500"

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "api_5xx" {
  display_name = "${local.name_prefix}-api-5xx-rate"
  combiner     = "OR"

  conditions {
    display_name = "api 5xx responses"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.api_5xx.name}\" AND resource.type=\"cloud_run_revision\""
      comparison      = "COMPARISON_GT"
      threshold_value = 10
      duration        = "300s"

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  depends_on = [google_project_service.services]
}

# HTTPS uptime check against the LB endpoint — only when a domain is configured.
resource "google_monitoring_uptime_check_config" "api" {
  count        = var.domain != "" ? 1 : 0
  display_name = "${local.name_prefix}-api-uptime"
  timeout      = "10s"
  period       = "300s"

  http_check {
    path         = "/api/v1/health"
    port         = 443
    use_ssl      = true
    validate_ssl = true
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.gcp_project_id
      host       = var.domain
    }
  }
}

# Cloud Armor enforces auth rate limits at the edge (CLAUDE.md mandates edge rate limiting).
# Rules mirror compose.prod.yml's Traefik limits. Cloud Armor rate_limit_options has a single
# window, so the login "5/min AND 10/hour" pair is split into two priority-distinct rules.
#
# No /internal/* source-range rule: there is no Pub/Sub push receiver (results go straight to
# Cloud SQL), so var.pubsub_push_source_ranges does not exist.
resource "google_compute_security_policy" "armor" {
  name = "${local.name_prefix}-armor"

  # /api/v1/auth/login — 5 requests / minute / IP.
  rule {
    action   = "throttle"
    priority = 1000
    match {
      expr {
        expression = "request.path.matches('/api/v1/auth/login')"
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = 5
        interval_sec = 60
      }
    }
    description = "auth login: 5/min/IP"
  }

  # /api/v1/auth/login — 10 requests / hour / IP.
  rule {
    action   = "throttle"
    priority = 1001
    match {
      expr {
        expression = "request.path.matches('/api/v1/auth/login')"
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = 10
        interval_sec = 3600
      }
    }
    description = "auth login: 10/hour/IP"
  }

  # /api/v1/auth/refresh — 30 requests / minute / IP.
  rule {
    action   = "throttle"
    priority = 1100
    match {
      expr {
        expression = "request.path.matches('/api/v1/auth/refresh')"
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = 30
        interval_sec = 60
      }
    }
    description = "auth refresh: 30/min/IP"
  }

  # Default: allow everything else.
  rule {
    action   = "allow"
    priority = 2147483647
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "default allow"
  }

  depends_on = [google_project_service.services]
}

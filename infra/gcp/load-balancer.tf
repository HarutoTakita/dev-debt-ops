# External global HTTPS load balancer fronting the api Cloud Run service, with Cloud Armor
# attached to the backend. The managed cert + HTTPS proxy + forwarding rule require a domain,
# so they are gated on var.domain (plan still passes with no domain — the NEG, backend,
# url map, IP and Armor policy are always created).
resource "google_compute_region_network_endpoint_group" "api" {
  name                  = "${local.name_prefix}-api-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"

  cloud_run {
    service = google_cloud_run_v2_service.api.name
  }
}

resource "google_compute_backend_service" "api" {
  name                  = "${local.name_prefix}-api-be"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"
  security_policy       = google_compute_security_policy.armor.id

  backend {
    group = google_compute_region_network_endpoint_group.api.id
  }
}

resource "google_compute_url_map" "api" {
  name            = "${local.name_prefix}-urlmap"
  default_service = google_compute_backend_service.api.id

  # Host-route the LP domain to the static backend bucket; everything else → the app (default).
  dynamic "host_rule" {
    for_each = local.lp_enabled ? [1] : []
    content {
      hosts        = [var.lp_domain]
      path_matcher = "landing"
    }
  }

  dynamic "path_matcher" {
    for_each = local.lp_enabled ? [1] : []
    content {
      name            = "landing"
      default_service = google_compute_backend_bucket.landing[0].id
    }
  }
}

resource "google_compute_global_address" "lb_ip" {
  name = "${local.name_prefix}-lb-ip"
}

resource "google_compute_managed_ssl_certificate" "api" {
  count = var.domain != "" ? 1 : 0
  name  = "${local.name_prefix}-cert"

  managed {
    # Single managed cert covers the app domain and (when set) the LP domain.
    domains = compact([var.domain, var.lp_domain])
  }
}

resource "google_compute_target_https_proxy" "api" {
  count            = var.domain != "" ? 1 : 0
  name             = "${local.name_prefix}-https-proxy"
  url_map          = google_compute_url_map.api.id
  ssl_certificates = [google_compute_managed_ssl_certificate.api[0].id]
}

resource "google_compute_global_forwarding_rule" "https" {
  count                 = var.domain != "" ? 1 : 0
  name                  = "${local.name_prefix}-https-fr"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  port_range            = "443"
  target                = google_compute_target_https_proxy.api[0].id
  ip_address            = google_compute_global_address.lb_ip.address
}

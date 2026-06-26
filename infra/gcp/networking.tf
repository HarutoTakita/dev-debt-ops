# Custom-mode VPC + subnet + Serverless VPC Access connector so Cloud Run can reach
# Cloud SQL over private IP and the internal `service` URL. Private service access
# (VPC peering) backs the prod private-IP database.
#
# Staging keeps the database on a public IP (see database.tf), so the private peering
# here is effectively prod-facing — created unconditionally to keep the graph simple
# (mirrors azure's "simplified networking for staging" stance, documented inline).
resource "google_compute_network" "main" {
  name                    = "${local.name_prefix}-vpc"
  auto_create_subnetworks = false

  depends_on = [google_project_service.services]
}

resource "google_compute_subnetwork" "main" {
  name          = "${local.name_prefix}-subnet"
  ip_cidr_range = "10.10.0.0/20"
  region        = var.region
  network       = google_compute_network.main.id

  private_ip_google_access = true
}

# Serverless VPC Access connector — Cloud Run egress into the VPC (Cloud SQL private IP,
# internal service-to-service).
resource "google_vpc_access_connector" "main" {
  name          = "${local.region_short}-${var.environment}-vpc-con"
  region        = var.region
  network       = google_compute_network.main.name
  ip_cidr_range = "10.8.0.0/28"
  # The API requires either instances or throughput bounds; use the smallest valid pair.
  min_instances = 2
  max_instances = 3

  depends_on = [google_project_service.services]
}

# Private service access (VPC peering range) for Cloud SQL private IP.
resource "google_compute_global_address" "private_ip_alloc" {
  name          = "${local.name_prefix}-psa"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.main.id
}

resource "google_service_networking_connection" "private_vpc" {
  network                 = google_compute_network.main.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_alloc.name]

  depends_on = [google_project_service.services]
}

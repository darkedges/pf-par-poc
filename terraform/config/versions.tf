terraform {
  required_version = ">= 1.9.0"
  required_providers {
    pingfederate = {
      source  = "pingidentity/pingfederate"
      version = "= 1.9.0"
    }
  }
}
provider "pingfederate" {
  https_host      = var.pf_admin_url
  product_version = "13.1"
}

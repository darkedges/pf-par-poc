terraform {
  required_version = ">= 1.9.0"
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "= 4.6.0"
    }
  }
}
variable "docker_host" {
  type        = string
  default     = "npipe:////./pipe/dockerDesktopLinuxEngine"
  description = "Docker Desktop Linux engine pipe on Windows. Override for other hosts."
}
provider "docker" {
  host = var.docker_host
}
variable "start_demo" {
  type        = bool
  default     = false
  description = "Start the demo only after configuring PingFederate and local TLS."
}
resource "docker_image" "demo" {
  count        = var.start_demo ? 1 : 0
  name         = "pf-par-demo:local"
  keep_locally = true
  build {
    context = abspath("${path.module}/../../demo")
  }
  triggers = {
    source = sha256(join("", [for f in ["Dockerfile", "requirements.txt", "app.py", "curl-walkthrough.md", "curl-walkthrough-bash.md", ".dockerignore"] : filesha256("${path.module}/../../demo/${f}")]))
  }
}
resource "docker_compose" "par" {
  project_name      = "pf-par-poc"
  project_directory = abspath("${path.module}/../..")
  config_paths      = [abspath("${path.module}/../../compose.yaml")]
  env_files         = [abspath("${path.module}/../../.env")]
  profiles          = var.start_demo ? ["demo"] : []
  wait              = true
  wait_timeout      = "10m"
  depends_on        = [docker_image.demo]
}
# The Compose provider does not detect a changed image behind the same tag.
# Reconcile only the demo service after image changes; preserve the PF runtime.
resource "terraform_data" "demo_rollout" {
  count            = var.start_demo ? 1 : 0
  triggers_replace = [docker_image.demo[0].image_id, docker_image.demo[0].triggers.source]
  depends_on       = [docker_compose.par]
  provisioner "local-exec" {
    command     = "docker compose --profile demo up --detach --no-deps demo"
    working_dir = abspath("${path.module}/../..")
    environment = { DOCKER_HOST = var.docker_host }
  }
}
output "compose_project" { value = docker_compose.par.id }

terraform {
  required_providers {
    yandex = {
      source = "yandex-cloud/yandex"
    }
    kubernetes = {
      source = "hashicorp/kubernetes"
    }
  }
}

provider "yandex" {
  token     = "y0__xDFi_vVAhjB3RMgtdK_uBKra2BZBV3g3qP4b5dd70wunq7IlA"
  cloud_id  = "b1gti7avnmd8ndstop5r"
  folder_id = "b1g95pme7edk23r055ej"
  zone      = "ru-central1-a"
}

provider "kubernetes" {
  host                   = yandex_kubernetes_cluster.tochka_cluster.master[0].external_v4_endpoint
  cluster_ca_certificate = yandex_kubernetes_cluster.tochka_cluster.master[0].cluster_ca_certificate
  token                  = data.yandex_client_config.client.iam_token
}

resource "yandex_kubernetes_cluster" "tochka_cluster" {
  name        = "tochka-cluster"
  description = "Kubernetes cluster for Tochka project"

  network_id = yandex_vpc_network.tochka_network.id

  master {
    version = "1.24"
    zonal {
      zone      = "ru-central1-a"
      subnet_id = yandex_vpc_subnet.tochka_subnet.id
    }

    public_ip = true

    maintenance_policy {
      auto_upgrade = true
    }
  }

  service_account_id      = yandex_iam_service_account.tochka_sa.id
  node_service_account_id = yandex_iam_service_account.tochka_sa.id

  depends_on = [
    yandex_resourcemanager_folder_iam_binding.k8s_clusters_sa_editor,
    yandex_resourcemanager_folder_iam_binding.vpc_public_admin,
    yandex_resourcemanager_folder_iam_binding.images_puller
  ]
}

resource "yandex_kubernetes_node_group" "tochka_node_group" {
  cluster_id = yandex_kubernetes_cluster.tochka_cluster.id
  name       = "tochka-node-group"

  instance_template {
    platform_id = "standard-v2"

    network_interface {
      nat        = true
      subnet_ids = [yandex_vpc_subnet.tochka_subnet.id]
    }

    resources {
      memory = 4
      cores  = 2
    }

    boot_disk {
      type = "network-hdd"
      size = 64
    }

    scheduling_policy {
      preemptible = false
    }

    container_runtime {
      type = "containerd"
    }
  }

  scale_policy {
    fixed_scale {
      size = 2
    }
  }

  allocation_policy {
    location {
      zone = "ru-central1-a"
    }
  }
}

resource "yandex_vpc_network" "tochka_network" {
  name = "tochka-network"
}

resource "yandex_vpc_subnet" "tochka_subnet" {
  name           = "tochka-subnet"
  zone           = "ru-central1-a"
  network_id     = yandex_vpc_network.tochka_network.id
  v4_cidr_blocks = ["10.10.0.0/16"]
}

resource "yandex_iam_service_account" "tochka_sa" {
  name        = "tochka-sa"
  description = "Service account for Tochka project"
}

resource "yandex_resourcemanager_folder_iam_binding" "k8s_clusters_sa_editor" {
  folder_id = "b1g95pme7edk23r055ej"
  role      = "editor"
  members   = [
    "serviceAccount:${yandex_iam_service_account.tochka_sa.id}",
  ]
}

resource "yandex_resourcemanager_folder_iam_binding" "vpc_public_admin" {
  folder_id = "b1g95pme7edk23r055ej"
  role      = "vpc.publicAdmin"
  members   = [
    "serviceAccount:${yandex_iam_service_account.tochka_sa.id}",
  ]
}

resource "yandex_resourcemanager_folder_iam_binding" "images_puller" {
  folder_id = "b1g95pme7edk23r055ej"
  role      = "container-registry.images.puller"
  members   = [
    "serviceAccount:${yandex_iam_service_account.tochka_sa.id}",
  ]
}

resource "kubernetes_namespace" "tochka" {
  metadata {
    name = "tochka"
  }
}

resource "kubernetes_deployment" "tochka" {
  metadata {
    name      = "tochka-deployment"
    namespace = kubernetes_namespace.tochka.metadata[0].name
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        project = "tochka"
      }
    }

    template {
      metadata {
        labels = {
          project = "tochka"
        }
      }

      spec {
        container {
          name  = "tochka"
          image = "cr.yandex/crprk26pj3fqbo2otsj4/tochka:latest"
          port {
            container_port = 5001
          }

          env {
            name  = "DATABASE_URL"
            value = "postgresql+asyncpg://postgres:1234@postgres:5432/Tochka"
          }
        }

        container {
          name  = "postgres"
          image = "postgres:17"

          env {
            name  = "POSTGRES_USER"
            value = "postgres"
          }

          env {
            name  = "POSTGRES_PASSWORD"
            value = "1234"
          }

          env {
            name  = "POSTGRES_DB"
            value = "Tochka"
          }

          port {
            container_port = 5432
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "tochka" {
  metadata {
    name      = "tochka-service"
    namespace = kubernetes_namespace.tochka.metadata[0].name
  }

  spec {
    selector = {
      project = "tochka"
    }

    port {
      name        = "app-listener"
      port        = 80
      target_port = 5001
      protocol    = "TCP"
    }
  }
}

resource "kubernetes_ingress" "tochka" {
  metadata {
    name      = "tochka-ingress"
    namespace = kubernetes_namespace.tochka.metadata[0].name

    annotations = {
      "nginx.ingress.kubernetes.io/use-regex"             = "true"
      "nginx.ingress.kubernetes.io/proxy-body-size"       = "50m"
      "nginx.ingress.kubernetes.io/proxy-read-timeout"   = "600"
      "nginx.ingress.kubernetes.io/proxy-send-timeout"    = "600"
      "nginx.org/websocket-services"                      = "tochka-service"
      "nginx.ingress.kubernetes.io/configuration-snippet" = <<-EOT
        proxy_set_header Upgrade "websocket";
        proxy_set_header Connection "Upgrade";
      EOT
    }
  }

  spec {
    ingress_class_name = "nginx"

    rule {
      host = "localhost"

      http {
        path {
          path = "/"
          path_type = "Prefix"

          backend {
            service {
              name = "tochka-service"
              port {
                number = 80
              }
            }
          }
        }
      }
    }
  }
}
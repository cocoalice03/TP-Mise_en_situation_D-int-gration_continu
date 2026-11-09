# Infrastructure de production sur Azure (spec §8).
#
# Terraform crée l'infrastructure : groupe de ressources, réseau, pare-feu, IP publique,
# VM avec Docker (installé au premier démarrage par cloud-init) et disque de données.
# L'application (MySQL, MinIO, traitement, cron) est ensuite déployée par le CD
# (.github/workflows/cd.yml) : Terraform ne manipule aucun mot de passe applicatif.

terraform {
  required_version = ">= 1.6"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

locals {
  tags = {
    project    = "transactions-pipeline"
    managed_by = "terraform"
  }

  # Ports ouverts uniquement aux adresses de var.admin_cidrs (aucune par défaut).
  admin_ports = {
    mysql         = { port = 3306, priority = 110 }
    minio-api     = { port = 9000, priority = 120 }
    minio-console = { port = 9001, priority = 130 }
  }
}

# --- Groupe de ressources -------------------------------------------------------------

resource "azurerm_resource_group" "main" {
  name     = "rg-${var.prefix}"
  location = var.location
  tags     = local.tags
}

# --- Réseau ---------------------------------------------------------------------------

resource "azurerm_virtual_network" "main" {
  name                = "vnet-${var.prefix}"
  address_space       = ["10.0.0.0/16"]
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags
}

resource "azurerm_subnet" "main" {
  name                 = "snet-${var.prefix}"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.1.0/24"]

  # Le sous-réseau ne référence le réseau que par son nom, qui ne change pas : sans
  # cette règle, recréer le réseau (ex. changement de région) laisserait Terraform
  # croire que l'ancien sous-réseau existe encore.
  lifecycle {
    replace_triggered_by = [azurerm_virtual_network.main.id]
  }
}

# Pare-feu : SSH ouvert (clé uniquement ; les adresses des runners GitHub du CD varient),
# MySQL et MinIO fermés sauf pour les adresses listées dans var.admin_cidrs.
resource "azurerm_network_security_group" "main" {
  name                = "nsg-${var.prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags

  security_rule {
    name                       = "allow-ssh"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  dynamic "security_rule" {
    for_each = length(var.admin_cidrs) > 0 ? local.admin_ports : {}
    content {
      name                       = "allow-${security_rule.key}"
      priority                   = security_rule.value.priority
      direction                  = "Inbound"
      access                     = "Allow"
      protocol                   = "Tcp"
      source_port_range          = "*"
      destination_port_range     = tostring(security_rule.value.port)
      source_address_prefixes    = var.admin_cidrs
      destination_address_prefix = "*"
    }
  }
}

resource "azurerm_subnet_network_security_group_association" "main" {
  subnet_id                 = azurerm_subnet.main.id
  network_security_group_id = azurerm_network_security_group.main.id
}

# IP statique : l'adresse (secret SSH_HOST du CD) ne change pas quand la VM redémarre.
resource "azurerm_public_ip" "main" {
  name                = "pip-${var.prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = local.tags
}

resource "azurerm_network_interface" "main" {
  name                = "nic-${var.prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.main.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.main.id
  }
}

# --- Machine virtuelle ----------------------------------------------------------------

resource "azurerm_linux_virtual_machine" "main" {
  name                  = "vm-${var.prefix}"
  location              = azurerm_resource_group.main.location
  resource_group_name   = azurerm_resource_group.main.name
  size                  = var.vm_size
  admin_username        = var.admin_username
  network_interface_ids = [azurerm_network_interface.main.id]
  tags                  = local.tags

  # Connexion par clé SSH uniquement.
  disable_password_authentication = true
  admin_ssh_key {
    username   = var.admin_username
    public_key = var.ssh_public_key
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
    disk_size_gb         = 30
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }

  # Premier démarrage : monte le disque de données sur /var/lib/docker puis installe Docker.
  custom_data = base64encode(templatefile("${path.module}/cloud-init.yaml.tftpl", {
    admin_username = var.admin_username
  }))
}

# --- Disque de données : volumes Docker (base MySQL et fichiers MinIO) -----------------
# Ressource séparée de la VM : les données survivent si la VM est recréée.

resource "azurerm_managed_disk" "data" {
  name                 = "disk-${var.prefix}-data"
  location             = azurerm_resource_group.main.location
  resource_group_name  = azurerm_resource_group.main.name
  storage_account_type = "StandardSSD_LRS"
  create_option        = "Empty"
  disk_size_gb         = var.data_disk_size_gb
  tags                 = local.tags
}

resource "azurerm_virtual_machine_data_disk_attachment" "data" {
  managed_disk_id    = azurerm_managed_disk.data.id
  virtual_machine_id = azurerm_linux_virtual_machine.main.id
  lun                = 0
  caching            = "None"
}

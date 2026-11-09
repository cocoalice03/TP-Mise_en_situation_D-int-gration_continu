variable "subscription_id" {
  description = "Identifiant de l'abonnement Azure (az account show --query id -o tsv)."
  type        = string
}

variable "location" {
  description = "Région Azure. Azure for Students n'autorise que germanywestcentral, denmarkeast, belgiumcentral, switzerlandnorth et austriaeast ; seule denmarkeast propose Standard_B2s à cet abonnement."
  type        = string
  default     = "denmarkeast"
}

variable "prefix" {
  description = "Préfixe des noms de ressources (rg-<prefix>, vm-<prefix>, ...)."
  type        = string
  # « dk » : groupe de ressources au nom neuf en denmarkeast (voir docs/terraform.md,
  # recréer un groupe supprimé sous le même nom dans une autre région provoque des 404).
  default = "transactions-dk"
}

variable "vm_size" {
  description = "Taille de la VM. B2s = 2 vCPU, 4 Go : MySQL 8.4 + MinIO + Docker à l'aise."
  type        = string
  default     = "Standard_B2s"
}

variable "admin_username" {
  description = "Utilisateur SSH de la VM (secret SSH_USER du CD)."
  type        = string
  default     = "azureuser"
}

variable "ssh_public_key" {
  description = "Clé publique SSH autorisée sur la VM (contenu de ~/.ssh/transactions_deploy.pub)."
  type        = string
}

variable "data_disk_size_gb" {
  description = "Taille du disque de données monté sur /var/lib/docker (volumes MySQL et MinIO)."
  type        = number
  default     = 32
}

variable "admin_cidrs" {
  description = "Adresses autorisées sur MySQL (3306) et MinIO (9000, 9001). Vide = ports fermés ; [\"0.0.0.0/0\"] = ouverts à tous."
  type        = list(string)
  default     = []
}

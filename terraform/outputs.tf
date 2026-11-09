output "resource_group" {
  description = "Groupe de ressources contenant toute l'infrastructure."
  value       = azurerm_resource_group.main.name
}

output "public_ip" {
  description = "IP publique de la VM (secret SSH_HOST du CD)."
  value       = azurerm_public_ip.main.ip_address
}

output "admin_username" {
  description = "Utilisateur SSH de la VM (secret SSH_USER du CD)."
  value       = var.admin_username
}

output "ssh_command" {
  description = "Commande de connexion à la VM."
  value       = "ssh -i ~/.ssh/transactions_deploy ${var.admin_username}@${azurerm_public_ip.main.ip_address}"
}

output "minio_console_url" {
  description = "Console MinIO (joignable seulement depuis admin_cidrs, sinon par tunnel SSH)."
  value       = "http://${azurerm_public_ip.main.ip_address}:9001"
}

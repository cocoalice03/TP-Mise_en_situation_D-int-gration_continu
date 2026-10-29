output "vm_public_ip" {
  description = "Adresse IP publique fixe (Elastic IP) de la VM (SSH_HOST dans le CD)"
  value       = aws_eip.vm_eip.public_ip
}

output "vm_public_dns" {
  description = "DNS public de la VM"
  value       = aws_instance.vm.public_dns
}

output "vpc_id" {
  description = "Identifiant du VPC créé pour l'environnement de production"
  value       = aws_vpc.main.id
}

output "ssh_command" {
  description = "Commande SSH pour se connecter à la VM"
  value       = "ssh ubuntu@${aws_eip.vm_eip.public_ip}"
}

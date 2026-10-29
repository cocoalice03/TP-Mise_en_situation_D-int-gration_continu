variable "aws_region" {
  description = "Région AWS où déployer les ressources"
  type        = string
  default     = "eu-west-3"
}

variable "project_name" {
  description = "Nom du projet utilisé pour taguer les ressources"
  type        = string
  default     = "transactions-pipeline"
}

variable "instance_type" {
  description = "Type d'instance EC2 pour la VM de production"
  type        = string
  default     = "t3.small"
}

variable "ssh_public_key" {
  description = "Clé publique SSH pour se connecter à la VM (utilisateur ubuntu)"
  type        = string
}

variable "allowed_ssh_cidr" {
  description = "Plage d'IP autorisée en SSH"
  type        = string
  default     = "0.0.0.0/0"
}

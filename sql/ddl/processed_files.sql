-- Suivi des fichiers déjà traités (anti-doublon, spec 4.7).
-- L'unicité porte sur le hash SHA-256 du contenu du fichier.
CREATE TABLE IF NOT EXISTS processed_files (
    id           INT          NOT NULL AUTO_INCREMENT,
    filename     VARCHAR(255) NOT NULL,
    file_hash    CHAR(64)     NOT NULL,
    rows_count   INT          NOT NULL,
    processed_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_processed_files_hash (file_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

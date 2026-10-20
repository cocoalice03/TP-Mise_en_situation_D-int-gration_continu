-- Transactions traitées (résultat du traitement, avec le flag is_high_value).
CREATE OR REPLACE TABLE transactions (
    id                   BIGINT        NOT NULL AUTO_INCREMENT,
    datetime_transaction DATETIME      NOT NULL,
    iban_origine         VARCHAR(34)   NOT NULL,
    pays_source          CHAR(2)       NOT NULL,
    banque_source        VARCHAR(100)  NOT NULL,
    iban_destinataire    VARCHAR(34)   NOT NULL,
    pays_destinataire    CHAR(2)       NOT NULL,
    montant              DECIMAL(12,2) NOT NULL,
    is_high_value        BOOLEAN       NOT NULL,
    PRIMARY KEY (id),
    KEY idx_transactions_iban_origine (iban_origine),
    KEY idx_transactions_banque_source (banque_source),
    KEY idx_transactions_iban_destinataire (iban_destinataire)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE observations
    ALTER COLUMN "identificationVerificationStatus" TYPE TEXT USING "identificationVerificationStatus"::text,
    ALTER COLUMN "idText[free_text]" TYPE TEXT USING "idText[free_text]"::text;

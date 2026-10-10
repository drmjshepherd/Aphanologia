CREATE TABLE observations_dropdown_backup AS
SELECT "observationID", "basisOfRecord", "idTechnique", "identificationVerificationStatus"
FROM observations;

BEGIN;
UPDATE observations SET "basisOfRecord" = 'Preserved specimen'
 WHERE lower(rtrim("basisOfRecord", '.')) = 'preserved specimen' AND "basisOfRecord" <> 'Preserved specimen';
UPDATE observations SET "basisOfRecord" = 'Still photograph'
 WHERE "basisOfRecord" = 'individual photograph(s)';
UPDATE observations SET "idTechnique" = 'Morphological identification'
 WHERE lower(rtrim("idTechnique", '.')) IN ('morphological identification','morphological observation','morphological')
   AND "idTechnique" <> 'Morphological identification';
UPDATE observations SET "idTechnique" = 'Automated image recognition'
 WHERE "idTechnique" = 'Image recognition';
-- check the row counts above, then:
COMMIT;   -- or ROLLBACK;

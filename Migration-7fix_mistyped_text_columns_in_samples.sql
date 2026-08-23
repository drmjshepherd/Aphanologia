ALTER TABLE samples
    ALTER COLUMN "samplingProtocol" TYPE TEXT USING "samplingProtocol"::text,
    ALTER COLUMN "samplesizeUnit" TYPE TEXT USING "samplesizeUnit"::text;

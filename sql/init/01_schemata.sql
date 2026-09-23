-- Vytvoří oddělená schémata pro jednotlivá prostředí.
-- Spouští se automaticky při prvním startu kontejneru (docker-entrypoint-initdb.d).
-- IF NOT EXISTS = skript je bezpečné spustit i opakovaně ručně.

CREATE SCHEMA IF NOT EXISTS dev;
CREATE SCHEMA IF NOT EXISTS test;
CREATE SCHEMA IF NOT EXISTS prod;

COMMENT ON SCHEMA dev  IS 'Vývoj – pokusy, lze kdykoli smazat';
COMMENT ON SCHEMA test IS 'Testování – ověřování načítání dat';
COMMENT ON SCHEMA prod IS 'Produkce – ověřená data z registrů';

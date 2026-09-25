DROP SCHEMA IF EXISTS kl012_fixture CASCADE;
DROP ROLE IF EXISTS kl012_application;
DROP ROLE IF EXISTS kl012_history_writer;
DROP ROLE IF EXISTS kl012_transition_owner;
DROP ROLE IF EXISTS kl012_originating_command;
DROP ROLE IF EXISTS kl012_outbox_dispatcher;

CREATE ROLE kl012_application NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE kl012_history_writer NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE kl012_transition_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE kl012_originating_command NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE kl012_outbox_dispatcher NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;

CREATE SCHEMA kl012_fixture;
REVOKE ALL ON SCHEMA kl012_fixture FROM PUBLIC;
GRANT USAGE ON SCHEMA kl012_fixture
    TO kl012_application, kl012_history_writer, kl012_transition_owner,
       kl012_originating_command, kl012_outbox_dispatcher;

CREATE TABLE kl012_fixture.immutable_history (
    history_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    content text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT transaction_timestamp()
);

CREATE FUNCTION kl012_fixture.reject_immutable_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $function$
BEGIN
    RAISE EXCEPTION 'KL_IMMUTABLE_HISTORY_MUTATION_REJECTED'
        USING ERRCODE = '55000';
END;
$function$;

CREATE TRIGGER immutable_history_reject_update_delete
BEFORE UPDATE OR DELETE ON kl012_fixture.immutable_history
FOR EACH ROW EXECUTE FUNCTION kl012_fixture.reject_immutable_mutation();

REVOKE ALL ON TABLE kl012_fixture.immutable_history FROM PUBLIC;
REVOKE ALL ON TABLE kl012_fixture.immutable_history
    FROM kl012_application, kl012_history_writer, kl012_transition_owner;
GRANT SELECT ON TABLE kl012_fixture.immutable_history TO kl012_application;
GRANT SELECT, INSERT ON TABLE kl012_fixture.immutable_history TO kl012_history_writer;
GRANT USAGE, SELECT ON SEQUENCE kl012_fixture.immutable_history_history_id_seq
    TO kl012_history_writer;

CREATE TABLE kl012_fixture.owned_transitions (
    entity_id bigint PRIMARY KEY,
    state text NOT NULL CHECK (state IN ('OPEN', 'SEALED')),
    revision integer NOT NULL DEFAULT 0 CHECK (revision >= 0)
);

CREATE FUNCTION kl012_fixture.guard_owned_transition()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $function$
BEGIN
    IF OLD.state <> 'OPEN' OR NEW.state <> 'SEALED' THEN
        RAISE EXCEPTION 'KL_INVALID_OWNED_TRANSITION'
            USING ERRCODE = '55000';
    END IF;
    IF NEW.entity_id <> OLD.entity_id OR NEW.revision <> OLD.revision + 1 THEN
        RAISE EXCEPTION 'KL_INVALID_OWNED_TRANSITION_SHAPE'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE TRIGGER owned_transition_guard
BEFORE UPDATE ON kl012_fixture.owned_transitions
FOR EACH ROW EXECUTE FUNCTION kl012_fixture.guard_owned_transition();

CREATE FUNCTION kl012_fixture.reject_owned_transition_delete()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $function$
BEGIN
    RAISE EXCEPTION 'KL_OWNED_TRANSITION_DELETE_REJECTED'
        USING ERRCODE = '55000';
END;
$function$;

CREATE TRIGGER owned_transition_reject_delete
BEFORE DELETE ON kl012_fixture.owned_transitions
FOR EACH ROW EXECUTE FUNCTION kl012_fixture.reject_owned_transition_delete();

REVOKE ALL ON TABLE kl012_fixture.owned_transitions FROM PUBLIC;
REVOKE ALL ON TABLE kl012_fixture.owned_transitions
    FROM kl012_application, kl012_history_writer, kl012_transition_owner;
GRANT SELECT ON TABLE kl012_fixture.owned_transitions TO kl012_application;
GRANT SELECT, INSERT, UPDATE ON TABLE kl012_fixture.owned_transitions
    TO kl012_transition_owner;

CREATE TABLE kl012_fixture.outbox_deliveries (
    event_id bigint PRIMARY KEY,
    destination text NOT NULL,
    delivery_status text NOT NULL CHECK (delivery_status IN ('PENDING', 'DELIVERED')),
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    UNIQUE (event_id, destination)
);

CREATE FUNCTION kl012_fixture.guard_outbox_delivery_update()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $function$
BEGIN
    IF NEW.event_id <> OLD.event_id OR NEW.destination <> OLD.destination THEN
        RAISE EXCEPTION 'KL_OUTBOX_BUSINESS_IDENTITY_MUTATION_REJECTED'
            USING ERRCODE = '55000';
    END IF;
    IF OLD.delivery_status <> 'PENDING' OR NEW.delivery_status <> 'DELIVERED' THEN
        RAISE EXCEPTION 'KL_INVALID_OUTBOX_DELIVERY_TRANSITION'
            USING ERRCODE = '55000';
    END IF;
    IF NEW.attempt_count <> OLD.attempt_count + 1 THEN
        RAISE EXCEPTION 'KL_INVALID_OUTBOX_ATTEMPT_COUNT'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE TRIGGER outbox_delivery_update_guard
BEFORE UPDATE ON kl012_fixture.outbox_deliveries
FOR EACH ROW EXECUTE FUNCTION kl012_fixture.guard_outbox_delivery_update();

REVOKE ALL ON TABLE kl012_fixture.outbox_deliveries FROM PUBLIC;
REVOKE ALL ON TABLE kl012_fixture.outbox_deliveries
    FROM kl012_application, kl012_history_writer, kl012_transition_owner,
         kl012_originating_command, kl012_outbox_dispatcher;
GRANT SELECT ON TABLE kl012_fixture.outbox_deliveries TO kl012_application;
GRANT SELECT, INSERT ON TABLE kl012_fixture.outbox_deliveries
    TO kl012_originating_command;
GRANT SELECT ON TABLE kl012_fixture.outbox_deliveries TO kl012_outbox_dispatcher;
GRANT UPDATE (delivery_status, attempt_count)
    ON TABLE kl012_fixture.outbox_deliveries TO kl012_outbox_dispatcher;

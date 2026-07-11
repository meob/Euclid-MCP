-- Extract cloud resources as Euclid facts
-- Output format: resource(name, env, encrypted, backup, public_access, classification),
--                resource_type(name, type), owner_team(name, team)

SELECT format('resource(%s, %s, %s, %s, %s, %s)',
    name,
    environment,
    CASE WHEN encrypted THEN 'encrypted' ELSE 'not_encrypted' END,
    CASE WHEN has_backup THEN 'has_backup' ELSE 'no_backup' END,
    CASE WHEN is_public THEN 'public_access' ELSE 'private_access' END,
    data_classification
) AS fact FROM cloud_resources
UNION ALL
SELECT format('resource_type(%s, %s)', name, resource_type) FROM cloud_resources
UNION ALL
SELECT format('owner_team(%s, %s)', name, owner_team) FROM cloud_resources;

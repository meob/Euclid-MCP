-- Extract roles and role hierarchy as Euclid facts
-- Output format: role(role_name), inherits(child, parent),
--                deploy_role_level(role_name, level)

SELECT format('role(%s)', name) AS fact FROM roles
UNION ALL
SELECT format('inherits(%s, %s)', child.name, parent.name)
FROM role_hierarchy rh
JOIN roles child ON rh.child_role_id = child.id
JOIN roles parent ON rh.parent_role_id = parent.id
UNION ALL
SELECT format('deploy_role_level(%s, %s)', name, level) FROM roles WHERE level IS NOT NULL;

-- Extract permissions as Euclid facts
-- Output format: permission(perm_name), role_permission(role_name, perm_name),
--                critical_operation(perm_name)

SELECT format('permission(%s)', name) AS fact FROM permissions
UNION ALL
SELECT format('role_permission(%s, %s)', r.name, p.name)
FROM role_permissions rp
JOIN roles r ON rp.role_id = r.id
JOIN permissions p ON rp.permission_id = p.id
UNION ALL
SELECT format('critical_operation(%s)', name) FROM permissions WHERE is_critical = true;

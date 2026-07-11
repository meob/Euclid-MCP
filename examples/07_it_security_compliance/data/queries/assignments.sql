-- Extract user-role assignments as Euclid facts
-- Output format: has_role(username, role_name)

SELECT format('has_role(%s, %s)', u.username, r.name) AS fact
FROM user_roles ur
JOIN users u ON ur.user_id = u.id
JOIN roles r ON ur.role_id = r.id
WHERE u.is_active = true;

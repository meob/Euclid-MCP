-- Extract active users as Euclid facts
-- Output format: user(username), department(username, dept_name),
--                account_type(username, type), mfa_enabled(username),
--                has_console_access(username), has_access_key(username),
--                last_login_days(username, days_since_login)

SELECT format('user(%s)', username) AS fact FROM users WHERE is_active = true
UNION ALL
SELECT format('department(%s, %s)', username, department) FROM users WHERE is_active = true
UNION ALL
SELECT format('account_type(%s, %s)', username, account_type) FROM users WHERE is_active = true
UNION ALL
SELECT format('mfa_enabled(%s)', username) FROM users WHERE is_active = true AND mfa_enabled = true
UNION ALL
SELECT format('has_console_access(%s)', username) FROM users WHERE is_active = true AND has_console_access = true
UNION ALL
SELECT format('has_access_key(%s)', username) FROM users WHERE is_active = true AND has_access_key = true
UNION ALL
SELECT format('last_login_days(%s, %s)', username, EXTRACT(DAY FROM CURRENT_DATE - last_login)::int)
FROM users WHERE is_active = true AND last_login IS NOT NULL
UNION ALL
SELECT format('rotate_keys_90d(%s)', username)
FROM users WHERE is_active = true AND last_key_rotation IS NOT NULL
    AND EXTRACT(DAY FROM CURRENT_DATE - last_key_rotation) <= 90;

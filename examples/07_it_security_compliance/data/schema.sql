-- IT Security & Compliance — PostgreSQL Schema
--
-- Standard RBAC schema compatible with most enterprise databases.
-- This schema defines the tables that extract_from_postgres.py queries.
-- For production use, adapt column names to match your existing schema.

-- ── Users ──
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100),
    department VARCHAR(50),
    is_active BOOLEAN DEFAULT true,
    account_type VARCHAR(20) DEFAULT 'human',  -- 'human', 'service', 'bot'
    has_console_access BOOLEAN DEFAULT true,
    has_access_key BOOLEAN DEFAULT false,
    mfa_enabled BOOLEAN DEFAULT false,
    last_login DATE,
    last_key_rotation DATE
);

-- ── Roles ──
CREATE TABLE roles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    level INT DEFAULT 0
);

-- ── Role Hierarchy (self-referencing) ──
CREATE TABLE role_hierarchy (
    child_role_id INT REFERENCES roles(id),
    parent_role_id INT REFERENCES roles(id),
    PRIMARY KEY (child_role_id, parent_role_id)
);

-- ── Permissions ──
CREATE TABLE permissions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    category VARCHAR(50),
    is_critical BOOLEAN DEFAULT false
);

-- ── Role → Permission assignments ──
CREATE TABLE role_permissions (
    role_id INT REFERENCES roles(id),
    permission_id INT REFERENCES permissions(id),
    PRIMARY KEY (role_id, permission_id)
);

-- ── User → Role assignments ──
CREATE TABLE user_roles (
    user_id INT REFERENCES users(id),
    role_id INT REFERENCES roles(id),
    assigned_date DATE DEFAULT CURRENT_DATE,
    PRIMARY KEY (user_id, role_id)
);

-- ── Cloud Resources ──
CREATE TABLE cloud_resources (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    resource_type VARCHAR(50),           -- 'ec2', 's3', 'rds', 'dynamodb', 'lambda'
    environment VARCHAR(20),             -- 'production', 'staging', 'development', 'golden'
    encrypted BOOLEAN DEFAULT false,
    has_backup BOOLEAN DEFAULT false,
    is_public BOOLEAN DEFAULT false,
    data_classification VARCHAR(20),     -- 'public', 'internal', 'confidential', 'secret'
    owner_team VARCHAR(50),
    created_date DATE DEFAULT CURRENT_DATE
);

-- ── Security Groups ──
CREATE TABLE security_groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    resource_id INT REFERENCES cloud_resources(id),
    allows_0_0_0_0 BOOLEAN DEFAULT false,
    allows_ssh_from_internet BOOLEAN DEFAULT false,
    allows_rdp_from_internet BOOLEAN DEFAULT false
);

-- ── Audit Log ──
CREATE TABLE audit_log (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id),
    action VARCHAR(100),
    resource_id INT REFERENCES cloud_resources(id),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_by INT REFERENCES users(id)
);

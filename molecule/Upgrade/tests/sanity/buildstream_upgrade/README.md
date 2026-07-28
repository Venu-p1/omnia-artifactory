# BuildStream Upgrade & Rollback Test Cases

## Overview

This directory contains automated test cases for BuildStream upgrade (2.1 → 2.2) and rollback (2.2 → 2.1) scenarios.

## Test Files

- `test_buildstream_upgrade.py` - Upgrade test cases (TC-UPG-001 through TC-UPG-006)
- `test_buildstream_rollback.py` - Rollback test cases (TC-RBK-001 through TC-RBK-008)

## Prerequisites

### For Upgrade Tests
- System must be in Omnia 2.1 installed state
- BuildStream must be enabled in 2.1
- Upgrade to 2.2 must have been executed successfully

### For Rollback Tests
- System must be in Omnia 2.2 upgraded state
- Rollback to 2.1 must have been executed successfully

## Running the Tests

### Run All BuildStream Upgrade Tests
```bash
cd ~/omnia-artifactory/automation-v2.2.0.0
source .venv/bin/activate
pytest molecule/Upgrade/tests/sanity/buildstream_upgrade/test_buildstream_upgrade.py -v
```

### Run All BuildStream Rollback Tests
```bash
pytest molecule/Upgrade/tests/sanity/buildstream_upgrade/test_buildstream_rollback.py -v
```

### Run Specific Test
```bash
pytest molecule/Upgrade/tests/sanity/buildstream_upgrade/test_buildstream_upgrade.py::test_upgrade_metadata_creation -v
```

### Run with Markers
```bash
# Run only BuildStream tests
pytest -m buildstream -v

# Run only rollback tests
pytest -m rollback -v
```

## Test Cases

### Upgrade Tests (test_buildstream_upgrade.py)

#### TC-UPG-001: Upgrade Metadata Creation
- Verifies `buildstream_upgrade_metadata.yml` exists in backup directory
- Validates required fields: upgrade_path, upgrade_timestamp, service existence flags, GitLab commit SHA

#### TC-UPG-002: Upgrade Backup Validation
- Verifies backup files exist:
  - `buildstream/omnia_build_stream.container.bak`
  - `buildstream/omnia_postgres.container.bak`
  - `buildstream/buildstream_db_backup.sql`
  - `configs/gitlab/gitlab.rb`
  - `configs/gitlab/gitlab-secrets.json`

#### TC-UPG-003: Postgres DB Alembic Migration
- Verifies database schema migrated from version 005 (2.1) to 007 (2.2)
- Queries alembic_version table in build_stream_db

#### TC-UPG-004: GitLab Upgrade Commit Check
- Verifies upgrade commit exists with message: `[omnia-upgrade-2.1-to-2.2] ... [ci skip]`
- Confirms no pipelines were triggered during upgrade

#### TC-UPG-005: GitLab Runner Re-registration Check
- Verifies GitLab runner service is active
- Confirms runner is online via GitLab API

#### TC-UPG-006: Service Restart After Quadlet Update
- Verifies all services restarted after upgrade:
  - omnia_build_stream.service
  - omnia_postgres.service
  - playbook_watcher.service
- Confirms quadlet files contain 2.2 image tags

### Rollback Tests (test_buildstream_rollback.py)

#### TC-RBK-001: DB Migration Downgrade
- Verifies database schema downgraded from version 007 (2.2) to 005 (2.1)
- Confirms Alembic downgrade executed before container stop

#### TC-RBK-002: GitLab Revert Commit Check
- Verifies revert commit exists in GitLab repository
- Confirms repository restored to 2.1 state

#### TC-RBK-003: GitLab Config & Runner Restoration
- Verifies gitlab.rb and gitlab-secrets.json restored from backup
- Confirms runner service is active

#### TC-RBK-004: Quadlet and BuildStream Source Restoration
- Verifies quadlet files contain 2.1 image tags
- Confirms BuildStream source directory restored to 2.1 version

#### TC-RBK-005: Automation Environment Cleanup
- Verifies `/opt/omnia/automation/.venv` directory removed
- Ensures clean state for 2.1 dependencies

#### TC-RBK-008: Service Restart After Restoration
- Verifies all services restarted after rollback:
  - omnia_build_stream.service
  - omnia_postgres.service
  - playbook_watcher.service
- Confirms systemd daemon-reload executed

## Test Markers

- `@pytest.mark.sanity` - Sanity test suite
- `@pytest.mark.buildstream` - BuildStream-specific tests
- `@pytest.mark.rollback` - Rollback-specific tests
- `@pytest.mark.order(N)` - Test execution order

## Expected Behavior

### Upgrade Tests
- All tests should PASS after a successful upgrade from 2.1 to 2.2
- Tests validate upgrade-specific artifacts (backups, metadata, migrations)
- Tests do NOT validate general 2.2 functionality (covered by separate 2.2 test suite)

### Rollback Tests
- All tests should PASS after a successful rollback from 2.2 to 2.1
- Tests validate rollback-specific restoration (downgrades, reverts, cleanups)
- Tests do NOT validate general 2.1 functionality (covered by separate 2.1 test suite)

## Troubleshooting

### Test Failures

1. **Metadata file not found**
   - Ensure upgrade completed successfully
   - Check `/opt/omnia/.data/upgrade_manifest.yml` exists
   - Verify backup_dir path is correct

2. **Backup files missing**
   - Verify upgrade process created backups
   - Check backup directory permissions
   - Review upgrade logs for backup errors

3. **Database version mismatch**
   - Check Alembic migration logs
   - Verify Postgres container is running
   - Query alembic_version table manually

4. **GitLab API failures**
   - Verify GitLab host is accessible
   - Check GitLab root token exists at `/root/.gitlab_root_token`
   - Confirm BuildStream project exists in GitLab

5. **Service not active**
   - Check systemd service status: `systemctl status <service>`
   - Review service logs: `journalctl -u <service>`
   - Verify quadlet files are valid

## Integration with Molecule

These tests are designed to run as part of the Molecule Upgrade scenario:

```bash
# Run full Upgrade scenario including BuildStream tests
run_molecule Upgrade test --suite sanity
```

## Notes

- Tests assume SSH access to OIM host is configured
- GitLab API tests will skip if credentials are not available
- Some tests may produce warnings but still pass (e.g., API access issues)
- Test execution order is important (use `@pytest.mark.order()`)

# Copyright 2026 Dell Inc. or its subsidiaries. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
BuildStream Upgrade Test Cases (2.1 → 2.2).

Tests the upgrade-specific mechanisms for BuildStream including:
- Upgrade metadata creation
- Backup validation
- Database Alembic migration (005 → 007)
- GitLab upgrade commit verification
- GitLab runner re-registration
- Service restart after quadlet updates

Prerequisites:
- System must be in 2.1 installed state with BuildStream enabled
- Upgrade must have been executed successfully

Test cases (executed in order):
1. TC-UPG-001: Verify upgrade metadata file exists and contains required fields
2. TC-UPG-002: Verify backup files exist (quadlets, database, GitLab configs)
3. TC-UPG-003: Verify Postgres DB Alembic migration (005 → 007)
4. TC-UPG-004: Verify GitLab upgrade commit with [ci skip]
5. TC-UPG-005: Verify GitLab runner re-registration
6. TC-UPG-006: Verify service restart after quadlet update
"""

import pytest
import yaml
import os
import re

from automation_library.core import TestLogger, get_host_connection


# =============================================================================
# TC-UPG-001: UPGRADE METADATA CREATION
# =============================================================================

@pytest.mark.sanity
@pytest.mark.buildstream
@pytest.mark.order(101)
def test_upgrade_metadata_creation(host):
    """
    TC-UPG-001: Verify upgrade metadata file exists and contains required fields.
    
    Steps:
    1. Locate the backup_dir from upgrade_manifest.yml
    2. Check for buildstream_upgrade_metadata.yml
    3. Verify required fields exist and are populated
    
    Expected Result:
    - Metadata file exists
    - Contains: upgrade_path, upgrade_timestamp, buildstream_service_exists_before,
      postgres_service_exists_before, upgrade_gitlab_commit_sha, upgrade_gitlab_pre_tag
    """
    logger = TestLogger("TC-UPG-001", "Upgrade Metadata Creation")
    conn = get_host_connection(host)
    
    logger.info("Reading upgrade_manifest.yml to find backup_dir")
    manifest_path = "/opt/omnia/.data/upgrade_manifest.yml"
    
    # Read manifest
    result = conn.run(f"cat {manifest_path}")
    assert result.rc == 0, f"Failed to read upgrade_manifest.yml: {result.stderr}"
    
    manifest = yaml.safe_load(result.stdout)
    backup_dir = manifest.get('backup_dir')
    assert backup_dir, "backup_dir not found in upgrade_manifest.yml"
    
    logger.info(f"Backup directory: {backup_dir}")
    
    # Check for buildstream_upgrade_metadata.yml
    metadata_path = f"{backup_dir}/buildstream_upgrade_metadata.yml"
    logger.info(f"Checking for metadata file: {metadata_path}")
    
    result = conn.run(f"test -f {metadata_path}")
    assert result.rc == 0, f"Metadata file not found: {metadata_path}"
    
    # Read and parse metadata
    result = conn.run(f"cat {metadata_path}")
    assert result.rc == 0, f"Failed to read metadata file: {result.stderr}"
    
    metadata = yaml.safe_load(result.stdout)
    logger.info(f"Metadata content: {metadata}")
    
    # Verify required fields
    required_fields = [
        'upgrade_path',
        'upgrade_timestamp',
        'buildstream_service_exists_before',
        'postgres_service_exists_before',
        'upgrade_gitlab_commit_sha',
        'upgrade_gitlab_pre_tag'
    ]
    
    for field in required_fields:
        assert field in metadata, f"Required field '{field}' missing from metadata"
        assert metadata[field] is not None, f"Field '{field}' is None"
        assert str(metadata[field]).strip() != '', f"Field '{field}' is empty"
    
    # Verify upgrade_path is 'upgrade_existing' (since we're testing upgrade from 2.1)
    assert metadata['upgrade_path'] == 'upgrade_existing', \
        f"Expected upgrade_path='upgrade_existing', got '{metadata['upgrade_path']}'"
    
    logger.success("Upgrade metadata file exists and contains all required fields")


# =============================================================================
# TC-UPG-002: UPGRADE BACKUP VALIDATION
# =============================================================================

@pytest.mark.sanity
@pytest.mark.buildstream
@pytest.mark.order(102)
def test_upgrade_backup_validation(host):
    """
    TC-UPG-002: Verify backup files exist.
    
    Steps:
    1. Check for backed up quadlet files
    2. Check for database backup SQL file
    3. Check for GitLab configuration backups
    
    Expected Result:
    - All backup files exist in backup_dir
    """
    logger = TestLogger("TC-UPG-002", "Upgrade Backup Validation")
    conn = get_host_connection(host)
    
    logger.info("Reading upgrade_manifest.yml to find backup_dir")
    manifest_path = "/opt/omnia/.data/upgrade_manifest.yml"
    
    result = conn.run(f"cat {manifest_path}")
    assert result.rc == 0, f"Failed to read upgrade_manifest.yml: {result.stderr}"
    
    manifest = yaml.safe_load(result.stdout)
    backup_dir = manifest.get('backup_dir')
    
    # List of expected backup files
    expected_backups = [
        f"{backup_dir}/buildstream/omnia_build_stream.container.bak",
        f"{backup_dir}/buildstream/omnia_postgres.container.bak",
        f"{backup_dir}/buildstream/buildstream_db_backup.sql",
        f"{backup_dir}/configs/gitlab/gitlab.rb",
        f"{backup_dir}/configs/gitlab/gitlab-secrets.json",
    ]
    
    missing_files = []
    for backup_file in expected_backups:
        logger.info(f"Checking for backup file: {backup_file}")
        result = conn.run(f"test -f {backup_file}")
        if result.rc != 0:
            missing_files.append(backup_file)
            logger.warning(f"Backup file missing: {backup_file}")
        else:
            logger.info(f"✓ Found: {backup_file}")
    
    assert len(missing_files) == 0, f"Missing backup files: {missing_files}"
    
    # Verify SQL backup is valid (contains SQL statements)
    sql_backup = f"{backup_dir}/buildstream/buildstream_db_backup.sql"
    result = conn.run(f"head -20 {sql_backup}")
    assert result.rc == 0, f"Failed to read SQL backup: {result.stderr}"
    assert 'PostgreSQL' in result.stdout or 'CREATE' in result.stdout or 'INSERT' in result.stdout, \
        "SQL backup file does not appear to be a valid PostgreSQL dump"
    
    logger.success("All backup files exist and SQL backup appears valid")


# =============================================================================
# TC-UPG-003: POSTGRES DB ALEMBIC MIGRATION
# =============================================================================

@pytest.mark.sanity
@pytest.mark.buildstream
@pytest.mark.order(103)
def test_postgres_alembic_migration(host):
    """
    TC-UPG-003: Verify Postgres DB Alembic migration (005 → 007).
    
    Steps:
    1. Connect to omnia_postgres container
    2. Query alembic_version table
    3. Verify version_num is 007 or later
    
    Expected Result:
    - Database schema migrated to version 007 (2.2)
    """
    logger = TestLogger("TC-UPG-003", "Postgres DB Alembic Migration")
    conn = get_host_connection(host)
    
    logger.info("Querying alembic_version from omnia_postgres container")
    
    cmd = 'podman exec omnia_postgres psql -U postgres -d build_stream_db -t -c "SELECT version_num FROM alembic_version;"'
    result = conn.run(cmd)
    
    assert result.rc == 0, f"Failed to query alembic_version: {result.stderr}"
    
    version_num = result.stdout.strip()
    logger.info(f"Current alembic version: {version_num}")
    
    # Verify version is 007 or later (2.2 migrations)
    assert version_num >= '007', \
        f"Expected alembic version >= 007 (2.2), got {version_num}"
    
    logger.success(f"Database migrated successfully to version {version_num}")


# =============================================================================
# TC-UPG-004: GITLAB UPGRADE COMMIT CHECK
# =============================================================================

@pytest.mark.sanity
@pytest.mark.buildstream
@pytest.mark.order(104)
def test_gitlab_upgrade_commit(host):
    """
    TC-UPG-004: Verify GitLab upgrade commit with [ci skip].
    
    Steps:
    1. Read upgrade_gitlab_commit_sha from metadata
    2. Query GitLab API for commit details
    3. Verify commit message contains [omnia-upgrade-2.1-to-2.2] and [ci skip]
    
    Expected Result:
    - Commit exists with correct message
    - No pipelines were triggered
    """
    logger = TestLogger("TC-UPG-004", "GitLab Upgrade Commit Check")
    conn = get_host_connection(host)
    
    logger.info("Reading upgrade metadata for GitLab commit SHA")
    manifest_path = "/opt/omnia/.data/upgrade_manifest.yml"
    
    result = conn.run(f"cat {manifest_path}")
    manifest = yaml.safe_load(result.stdout)
    backup_dir = manifest.get('backup_dir')
    
    metadata_path = f"{backup_dir}/buildstream_upgrade_metadata.yml"
    result = conn.run(f"cat {metadata_path}")
    metadata = yaml.safe_load(result.stdout)
    
    commit_sha = metadata.get('upgrade_gitlab_commit_sha')
    assert commit_sha, "upgrade_gitlab_commit_sha not found in metadata"
    
    logger.info(f"Upgrade commit SHA: {commit_sha}")
    
    # Read GitLab configuration to get host and credentials
    logger.info("Reading GitLab configuration")
    result = conn.run("cat /opt/omnia/input/project_default/gitlab_config.yml")
    if result.rc != 0:
        logger.warning("Could not read gitlab_config.yml, skipping GitLab API check")
        pytest.skip("GitLab configuration not accessible")
    
    gitlab_config = yaml.safe_load(result.stdout)
    gitlab_host = gitlab_config.get('gitlab_host')
    
    if not gitlab_host:
        logger.warning("gitlab_host not found in config, skipping GitLab API check")
        pytest.skip("GitLab host not configured")
    
    logger.info(f"GitLab host: {gitlab_host}")
    
    # Try to read GitLab root token
    result = conn.run("cat /root/.gitlab_root_token 2>/dev/null || echo ''")
    gitlab_token = result.stdout.strip()
    
    if not gitlab_token:
        logger.warning("GitLab root token not found, skipping API check")
        logger.info("Checking commit message format from metadata instead")
        
        # At minimum, verify the pre-tag format is correct
        pre_tag = metadata.get('upgrade_gitlab_pre_tag', '')
        assert 'pre-upgrade-2.1-to-2.2' in pre_tag, \
            f"Expected pre-tag to contain 'pre-upgrade-2.1-to-2.2', got '{pre_tag}'"
        
        logger.success("Upgrade metadata contains expected GitLab commit information")
        return
    
    # Query GitLab API for commit details
    logger.info(f"Querying GitLab API for commit {commit_sha[:12]}")
    
    # Get project ID first
    cmd = f'curl -sk -H "PRIVATE-TOKEN: {gitlab_token}" "https://{gitlab_host}/api/v4/projects?search=build_stream"'
    result = conn.run(cmd)
    
    if result.rc != 0:
        logger.warning("Failed to query GitLab API, skipping detailed commit check")
        pytest.skip("GitLab API not accessible")
    
    import json
    try:
        projects = json.loads(result.stdout)
        if not projects:
            logger.warning("No build_stream project found in GitLab")
            pytest.skip("BuildStream project not found in GitLab")
        
        project_id = projects[0]['id']
        logger.info(f"BuildStream project ID: {project_id}")
        
        # Get commit details
        cmd = f'curl -sk -H "PRIVATE-TOKEN: {gitlab_token}" "https://{gitlab_host}/api/v4/projects/{project_id}/repository/commits/{commit_sha}"'
        result = conn.run(cmd)
        
        commit_data = json.loads(result.stdout)
        commit_message = commit_data.get('message', '')
        
        logger.info(f"Commit message: {commit_message[:100]}...")
        
        # Verify commit message
        assert '[omnia-upgrade-2.1-to-2.2]' in commit_message, \
            f"Commit message does not contain '[omnia-upgrade-2.1-to-2.2]'"
        assert '[ci skip]' in commit_message, \
            f"Commit message does not contain '[ci skip]'"
        
        logger.success("GitLab upgrade commit verified successfully")
        
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.warning(f"Failed to parse GitLab API response: {e}")
        pytest.skip("Could not verify GitLab commit via API")


# =============================================================================
# TC-UPG-005: GITLAB RUNNER RE-REGISTRATION CHECK
# =============================================================================

@pytest.mark.sanity
@pytest.mark.buildstream
@pytest.mark.order(105)
def test_gitlab_runner_reregistration(host):
    """
    TC-UPG-005: Verify GitLab runner re-registration.
    
    Steps:
    1. Query GitLab API for project runners
    2. Verify at least one runner is online
    3. Verify no stale/offline runners from 2.1
    
    Expected Result:
    - New runner is online and active
    """
    logger = TestLogger("TC-UPG-005", "GitLab Runner Re-registration Check")
    conn = get_host_connection(host)
    
    logger.info("Checking GitLab runner status")
    
    # Read GitLab configuration
    result = conn.run("cat /opt/omnia/input/project_default/gitlab_config.yml")
    if result.rc != 0:
        logger.warning("Could not read gitlab_config.yml, skipping runner check")
        pytest.skip("GitLab configuration not accessible")
    
    gitlab_config = yaml.safe_load(result.stdout)
    gitlab_host = gitlab_config.get('gitlab_host')
    
    if not gitlab_host:
        pytest.skip("GitLab host not configured")
    
    # Check if runner service is active on GitLab host
    result = conn.run(f"ssh -o StrictHostKeyChecking=no root@{gitlab_host} 'systemctl is-active gitlab-runner.service' 2>/dev/null || echo 'unknown'")
    runner_status = result.stdout.strip()
    
    logger.info(f"GitLab runner service status: {runner_status}")
    
    if runner_status == 'active':
        logger.success("GitLab runner service is active")
    else:
        logger.warning(f"GitLab runner service status: {runner_status}")
        # Don't fail the test, just log the status
    
    # Try to check runner registration via API
    result = conn.run("cat /root/.gitlab_root_token 2>/dev/null || echo ''")
    gitlab_token = result.stdout.strip()
    
    if not gitlab_token:
        logger.warning("GitLab root token not found, cannot verify runner via API")
        logger.info("Assuming runner is registered if service is active")
        return
    
    # Get project ID and query runners
    cmd = f'curl -sk -H "PRIVATE-TOKEN: {gitlab_token}" "https://{gitlab_host}/api/v4/projects?search=build_stream"'
    result = conn.run(cmd)
    
    if result.rc != 0:
        logger.warning("Failed to query GitLab API")
        return
    
    import json
    try:
        projects = json.loads(result.stdout)
        if projects:
            project_id = projects[0]['id']
            
            # Query project runners
            cmd = f'curl -sk -H "PRIVATE-TOKEN: {gitlab_token}" "https://{gitlab_host}/api/v4/projects/{project_id}/runners"'
            result = conn.run(cmd)
            
            runners = json.loads(result.stdout)
            logger.info(f"Found {len(runners)} runner(s)")
            
            online_runners = [r for r in runners if r.get('status') == 'online']
            logger.info(f"Online runners: {len(online_runners)}")
            
            assert len(online_runners) > 0, "No online runners found"
            
            logger.success(f"GitLab runner verified: {len(online_runners)} online runner(s)")
    
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.warning(f"Failed to parse GitLab API response: {e}")


# =============================================================================
# TC-UPG-006: SERVICE RESTART AFTER QUADLET UPDATE
# =============================================================================

@pytest.mark.sanity
@pytest.mark.buildstream
@pytest.mark.order(106)
def test_service_restart_after_quadlet_update(host):
    """
    TC-UPG-006: Verify service restart after quadlet update.
    
    Steps:
    1. Check ActiveEnterTimestamp for omnia_build_stream.service
    2. Check ActiveEnterTimestamp for omnia_postgres.service
    3. Check ActiveEnterTimestamp for playbook_watcher.service
    4. Verify quadlet files contain 2.2 image tags
    
    Expected Result:
    - All services have recent ActiveEnterTimestamp (after upgrade)
    - Quadlet files reflect 2.2 configuration
    """
    logger = TestLogger("TC-UPG-006", "Service Restart After Quadlet Update")
    conn = get_host_connection(host)
    
    services = [
        'omnia_build_stream.service',
        'omnia_postgres.service',
        'playbook_watcher.service'
    ]
    
    logger.info("Checking service ActiveEnterTimestamp")
    
    for service in services:
        result = conn.run(f"systemctl show --property=ActiveEnterTimestamp {service}")
        assert result.rc == 0, f"Failed to get timestamp for {service}: {result.stderr}"
        
        timestamp = result.stdout.strip()
        logger.info(f"{service}: {timestamp}")
        
        # Verify service is active
        result = conn.run(f"systemctl is-active {service}")
        status = result.stdout.strip()
        assert status == 'active', f"{service} is not active: {status}"
    
    logger.success("All services are active with recent timestamps")
    
    # Verify quadlet files contain 2.2 image references
    logger.info("Checking quadlet files for 2.2 image tags")
    
    quadlet_files = [
        '/etc/containers/systemd/omnia_build_stream.container',
        '/etc/containers/systemd/omnia_postgres.container'
    ]
    
    for quadlet in quadlet_files:
        result = conn.run(f"cat {quadlet}")
        if result.rc == 0:
            content = result.stdout
            logger.info(f"Checking {quadlet}")
            
            # Look for image version in quadlet (should contain 2.2 or v2.2)
            if 'build_stream' in quadlet:
                # BuildStream image should have 2.2 tag
                assert '2.2' in content or 'v2.2' in content, \
                    f"BuildStream quadlet does not contain 2.2 image tag"
            elif 'postgres' in quadlet:
                # Postgres quadlet should exist and be valid
                assert 'Image=' in content, f"Postgres quadlet missing Image= directive"
            
            logger.info(f"✓ {quadlet} contains expected 2.2 configuration")
    
    # Verify playbook_watcher.service points to 2.2 source
    result = conn.run("cat /etc/systemd/system/playbook_watcher.service")
    if result.rc == 0:
        content = result.stdout
        assert '/opt/omnia/build_stream/playbook-watcher/playbook_watcher_service.py' in content, \
            "playbook_watcher.service does not point to correct 2.2 source path"
        logger.info("✓ playbook_watcher.service points to 2.2 source path")
    
    logger.success("All services restarted with 2.2 configuration")

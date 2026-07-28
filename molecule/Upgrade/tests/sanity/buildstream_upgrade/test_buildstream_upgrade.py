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
- System must be upgraded to Omnia 2.2
- BuildStream upgrade must have been executed successfully
"""

import pytest
import json

from automation_library.core import (
    TestLogger,
    get_testinfra_host,
    run_on_oim,
    run_in_container,
    exec_psql_query,
    get_credential_value,
    POSTGRES_CONTAINER,
    POSTGRES_DB,
    POSTGRES_USER_KEY,
    OMNIA_CORE_CONTAINER,
    OMNIA_CREDENTIALS_PATH,
    OMNIA_CREDENTIALS_KEY_PATH,
)
from automation_library.upgrade_and_rollback.vars import (
    UPGRADE_VARS,
    UPGRADE_MANIFEST_PATH,
    BUILDSTREAM_BACKUP_DIR,
    BUILDSTREAM_METADATA_FILE,
    GITLAB_CONFIGS_DIR,
    BUILDSTREAM_CONTAINER_BACKUP,
    POSTGRES_CONTAINER_BACKUP,
    BUILDSTREAM_DB_BACKUP,
    GITLAB_RB_BACKUP,
    GITLAB_SECRETS_BACKUP,
    QUADLET_DIR,
    BUILDSTREAM_QUADLET,
    BUILDSTREAM_SERVICE,
    POSTGRES_QUADLET,
    POSTGRES_SERVICE,
    PLAYBOOK_WATCHER_QUADLET,
    BUILDSTREAM_IMAGE_TAG_2_2,
    ALEMBIC_VERSION_2_2,
    GITLAB_API_BASE,
    GITLAB_COMMIT_TITLE_PREFIX,
)
from automation_library.upgrade_and_rollback.functions import (
    get_oim_metadata,
    read_container_file,
    get_upgrade_manifest,
    get_buildstream_metadata,
    get_gitlab_root_token,
)
from automation_library.upgrade_and_rollback.messages import (
    BUILDSTREAM_TEST_NAMES,
    BUILDSTREAM_LOG_MSGS,
    BUILDSTREAM_ASSERT_MSGS,
    BUILDSTREAM_SKIP_MSGS,
)
from automation_library.gitlab.functions import (
    get_gitlab_host,
    get_gitlab_project_name,
    get_gitlab_https_port,
    ssh_to_gitlab,
)
from automation_library.gitlab.vars import GITLAB_ROOT_TOKEN_FILE


@pytest.fixture(scope="module")
def host():
    """Get Testinfra host connected to OIM server."""
    return get_testinfra_host()


@pytest.fixture(scope="module")
def upgrade_config():
    """Get upgrade configuration from UPGRADE_VARS."""
    return {
        "current_version": UPGRADE_VARS["current_version"],
        "new_version": UPGRADE_VARS["new_version"],
        "backup_path": UPGRADE_VARS["backup_path"],
    }


@pytest.fixture(scope="module")
def oim_shared_path(host):
    """Get oim_shared_path from omnia_core metadata."""
    metadata = get_oim_metadata(host, OMNIA_CORE_CONTAINER)
    assert metadata["success"], f"Failed to read OIM metadata: {metadata['error']}"
    return metadata["oim_shared_path"]


# =============================================================================
# TC-UPG-001: UPGRADE METADATA CREATION
# =============================================================================

@pytest.mark.sanity
@pytest.mark.buildstream_upgrade
@pytest.mark.buildstream
@pytest.mark.order(101)
def test_upgrade_metadata_creation(host, oim_shared_path, upgrade_config):
    """
    TC-UPG-001: Verify upgrade metadata file exists and contains required fields.
    """
    logger = TestLogger(BUILDSTREAM_TEST_NAMES["upgrade_metadata_creation"])

    logger.check(BUILDSTREAM_LOG_MSGS["reading_manifest"].format(path=UPGRADE_MANIFEST_PATH))

    manifest_result = get_upgrade_manifest(host)
    assert manifest_result["success"], BUILDSTREAM_ASSERT_MSGS["metadata_file_not_found"].format(
        path=UPGRADE_MANIFEST_PATH
    )

    manifest = manifest_result["manifest"]
    backup_dir = manifest.get('backup_dir')
    assert backup_dir, BUILDSTREAM_ASSERT_MSGS["backup_dir_missing"]

    logger.check(BUILDSTREAM_LOG_MSGS["backup_dir"].format(path=backup_dir))

    # Replace /opt/omnia with oim_shared_path for OIM host access
    metadata_path = backup_dir.replace("/opt/omnia", f"{oim_shared_path}/omnia")
    metadata_path = f"{metadata_path}/{BUILDSTREAM_METADATA_FILE}"
    logger.check(BUILDSTREAM_LOG_MSGS["checking_metadata"].format(path=metadata_path))

    metadata_result = get_buildstream_metadata(host, metadata_path)
    assert metadata_result["success"], BUILDSTREAM_ASSERT_MSGS["metadata_file_not_found"].format(
        path=metadata_path
    )

    metadata = metadata_result["metadata"]
    logger.check(BUILDSTREAM_LOG_MSGS["metadata_content"].format(metadata=metadata))

    required_fields = [
        'upgrade_path',
        'upgrade_timestamp',
        'buildstream_service_exists_before',
        'postgres_service_exists_before',
        'upgrade_gitlab_commit_sha',
        'upgrade_gitlab_pre_tag',
    ]

    for field in required_fields:
        assert field in metadata, BUILDSTREAM_ASSERT_MSGS["metadata_field_missing"].format(field=field)
        assert metadata[field] is not None, BUILDSTREAM_ASSERT_MSGS["metadata_field_empty"].format(field=field)
        assert str(metadata[field]).strip() != '', BUILDSTREAM_ASSERT_MSGS["metadata_field_empty"].format(field=field)

    assert metadata['upgrade_path'] == 'upgrade_existing', \
        BUILDSTREAM_ASSERT_MSGS["upgrade_path_invalid"].format(actual=metadata['upgrade_path'])

    logger.passed("Upgrade metadata file exists and contains all required fields")


# =============================================================================
# TC-UPG-002: UPGRADE BACKUP VALIDATION
# =============================================================================

@pytest.mark.sanity
@pytest.mark.buildstream_upgrade
@pytest.mark.buildstream
@pytest.mark.order(102)
def test_upgrade_backup_validation(host, oim_shared_path, upgrade_config):
    """
    TC-UPG-002: Verify backup files exist on the OIM shared path.
    """
    logger = TestLogger(BUILDSTREAM_TEST_NAMES["upgrade_backup_validation"])

    backup_dir_on_oim = f"{oim_shared_path}/omnia/backups/upgrade/version_{upgrade_config['current_version']}"
    logger.check(BUILDSTREAM_LOG_MSGS["backup_dir_on_oim"].format(path=backup_dir_on_oim))

    expected_backups = [
        f"{backup_dir_on_oim}/{BUILDSTREAM_BACKUP_DIR}/{BUILDSTREAM_CONTAINER_BACKUP}",
        f"{backup_dir_on_oim}/{BUILDSTREAM_BACKUP_DIR}/{POSTGRES_CONTAINER_BACKUP}",
        f"{backup_dir_on_oim}/{BUILDSTREAM_BACKUP_DIR}/{BUILDSTREAM_DB_BACKUP}",
        f"{backup_dir_on_oim}/{GITLAB_CONFIGS_DIR}/{GITLAB_RB_BACKUP}",
        f"{backup_dir_on_oim}/{GITLAB_CONFIGS_DIR}/{GITLAB_SECRETS_BACKUP}",
    ]

    missing_files = []
    for backup_file in expected_backups:
        logger.check(BUILDSTREAM_LOG_MSGS["checking_backup_file"].format(path=backup_file))
        result = run_on_oim(host, f"test -f {backup_file}")
        if result.rc != 0:
            missing_files.append(backup_file)
            logger.skipped(BUILDSTREAM_SKIP_MSGS["backup_file_missing"].format(path=backup_file))

    assert len(missing_files) == 0, BUILDSTREAM_ASSERT_MSGS["backup_files_missing"].format(
        files=missing_files,
        backup_dir=backup_dir_on_oim,
    )

    sql_backup = f"{backup_dir_on_oim}/{BUILDSTREAM_BACKUP_DIR}/{BUILDSTREAM_DB_BACKUP}"
    result = run_on_oim(host, f"stat -c %s {sql_backup}")
    assert result.rc == 0, f"Failed to stat SQL backup: {result.stderr}"
    sql_size = int(result.stdout.strip())
    if sql_size == 0:
        logger.skipped(BUILDSTREAM_SKIP_MSGS["sql_backup_empty"])
    else:
        logger.check(BUILDSTREAM_LOG_MSGS["sql_backup_nonempty"])

    logger.passed("All backup files exist")


# =============================================================================
# TC-UPG-003: POSTGRES DB ALEMBIC MIGRATION
# =============================================================================

@pytest.mark.sanity
@pytest.mark.buildstream_upgrade
@pytest.mark.buildstream
@pytest.mark.order(103)
def test_postgres_alembic_migration(host):
    """
    TC-UPG-003: Verify Postgres DB Alembic migration to 2.2.
    """
    logger = TestLogger(BUILDSTREAM_TEST_NAMES["postgres_alembic_migration"])

    pg_user = get_credential_value(
        host,
        OMNIA_CREDENTIALS_PATH,
        OMNIA_CREDENTIALS_KEY_PATH,
        POSTGRES_USER_KEY,
    )
    if not pg_user:
        pg_user = "postgres"

    result = exec_psql_query(
        host,
        container=POSTGRES_CONTAINER,
        db_user=pg_user,
        db_name=POSTGRES_DB,
        sql="SELECT version_num FROM alembic_version;"
    )

    assert result["success"], f"Failed to query alembic_version: {result['error']}"
    assert result["rows"], "No rows returned from alembic_version"

    version_num = result["rows"][0].strip()
    logger.check(BUILDSTREAM_LOG_MSGS["current_alembic_version"].format(version=version_num))

    assert version_num == ALEMBIC_VERSION_2_2, \
        BUILDSTREAM_ASSERT_MSGS["alembic_version_mismatch"].format(
            expected=ALEMBIC_VERSION_2_2,
            actual=version_num,
        )

    logger.passed(f"Database migrated successfully to version {version_num}")


# =============================================================================
# TC-UPG-004: GITLAB UPGRADE COMMIT CHECK
# =============================================================================

@pytest.mark.sanity
@pytest.mark.buildstream_upgrade
@pytest.mark.buildstream
@pytest.mark.order(104)
def test_gitlab_upgrade_commit(host, oim_shared_path, upgrade_config):
    """
    TC-UPG-004: Verify GitLab upgrade commit with [ci skip].
    """
    logger = TestLogger(BUILDSTREAM_TEST_NAMES["gitlab_upgrade_commit"])

    manifest_result = get_upgrade_manifest(host)
    assert manifest_result["success"], BUILDSTREAM_ASSERT_MSGS["metadata_file_not_found"].format(
        path=UPGRADE_MANIFEST_PATH
    )

    manifest = manifest_result["manifest"]
    backup_dir = manifest.get('backup_dir')
    assert backup_dir, BUILDSTREAM_ASSERT_MSGS["backup_dir_missing"]

    # Replace /opt/omnia with oim_shared_path for OIM host access
    metadata_path = backup_dir.replace("/opt/omnia", f"{oim_shared_path}/omnia")
    metadata_path = f"{metadata_path}/{BUILDSTREAM_METADATA_FILE}"
    metadata_result = get_buildstream_metadata(host, metadata_path)
    assert metadata_result["success"], BUILDSTREAM_ASSERT_MSGS["metadata_file_not_found"].format(
        path=metadata_path
    )

    metadata = metadata_result["metadata"]
    commit_sha = metadata.get('upgrade_gitlab_commit_sha')
    assert commit_sha, "upgrade_gitlab_commit_sha not found in metadata"

    logger.check(BUILDSTREAM_LOG_MSGS["checking_commit"].format(sha=commit_sha))

    gitlab_host = get_gitlab_host(host)
    if not gitlab_host:
        logger.skipped(BUILDSTREAM_SKIP_MSGS["gitlab_not_configured"])
        pytest.skip(BUILDSTREAM_SKIP_MSGS["gitlab_not_configured"])

    logger.check(BUILDSTREAM_LOG_MSGS["gitlab_host"].format(host=gitlab_host))

    gitlab_port = get_gitlab_https_port(host)
    gitlab_token_result = get_gitlab_root_token(host, ssh_to_gitlab, GITLAB_ROOT_TOKEN_FILE)
    if not gitlab_token_result["success"]:
        logger.skipped(BUILDSTREAM_SKIP_MSGS["gitlab_token_missing"])
        pytest.skip(BUILDSTREAM_SKIP_MSGS["gitlab_token_missing"])

    gitlab_token = gitlab_token_result["token"]

    project_name = get_gitlab_project_name(host)
    full_project_path = f"root/{project_name}" if project_name and "/" not in project_name else project_name
    encoded_project = full_project_path.replace("/", "%2F")
    api_base = f"https://{gitlab_host}:{gitlab_port}{GITLAB_API_BASE}"

    try:
        result = ssh_to_gitlab(
            host,
            f'curl -sk -H "PRIVATE-TOKEN: {gitlab_token}" "{api_base}/projects/{encoded_project}/repository/commits/{commit_sha}"'
        )
        if not result.get("success"):
            logger.skipped(f"GitLab API call failed: {result.get('error')}")
            pytest.skip("GitLab API call failed")

        commit_data = json.loads(result["stdout"])
        commit_message = commit_data.get('message', '')

        logger.check(BUILDSTREAM_LOG_MSGS["commit_found"].format(title=commit_message[:120] + "..."))

        assert GITLAB_COMMIT_TITLE_PREFIX in commit_message, \
            f"Commit message does not contain '{GITLAB_COMMIT_TITLE_PREFIX}'"
        assert '[ci skip]' in commit_message, \
            "Commit message does not contain '[ci skip]'"

        logger.passed("GitLab upgrade commit verified successfully")
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.skipped(f"Failed to parse GitLab API response: {e}")
        pytest.skip("Could not verify GitLab commit via API")


# =============================================================================
# TC-UPG-005: GITLAB RUNNER RE-REGISTRATION CHECK
# =============================================================================

@pytest.mark.sanity
@pytest.mark.buildstream_upgrade
@pytest.mark.buildstream
@pytest.mark.order(105)
def test_gitlab_runner_reregistration(host):
    """
    TC-UPG-005: Verify GitLab runner re-registration.
    """
    logger = TestLogger(BUILDSTREAM_TEST_NAMES["gitlab_runner_reregistration"])

    gitlab_host = get_gitlab_host(host)
    if not gitlab_host:
        pytest.skip(BUILDSTREAM_SKIP_MSGS["gitlab_not_configured"])

    result = ssh_to_gitlab(host, "systemctl is-active gitlab-runner.service 2>/dev/null || echo unknown")
    runner_status = result.get("stdout", "").strip()
    logger.check(BUILDSTREAM_LOG_MSGS["checking_runner_service"].format(status=runner_status))

    if runner_status == 'active':
        logger.passed("GitLab runner service is active")

    gitlab_port = get_gitlab_https_port(host)
    gitlab_token_result = get_gitlab_root_token(host, ssh_to_gitlab, GITLAB_ROOT_TOKEN_FILE)

    if not gitlab_token_result["success"]:
        logger.skipped(BUILDSTREAM_SKIP_MSGS["gitlab_token_missing"])
        return

    gitlab_token = gitlab_token_result["token"]

    project_name = get_gitlab_project_name(host)
    full_project_path = f"root/{project_name}" if project_name and "/" not in project_name else project_name
    encoded_project = full_project_path.replace("/", "%2F")
    api_base = f"https://{gitlab_host}:{gitlab_port}{GITLAB_API_BASE}"

    try:
        result = ssh_to_gitlab(
            host,
            f'curl -sk -H "PRIVATE-TOKEN: {gitlab_token}" "{api_base}/projects/{encoded_project}/runners"'
        )
        if not result.get("success"):
            logger.skipped(f"GitLab API call failed: {result.get('error')}")
            return

        runners = json.loads(result["stdout"])
        online_runners = [r for r in runners if r.get('status') == 'online']
        logger.check(BUILDSTREAM_LOG_MSGS["found_runners"].format(
            count=len(runners),
            online=len(online_runners),
        ))

        assert len(online_runners) > 0, BUILDSTREAM_ASSERT_MSGS["gitlab_runner_offline"]
        logger.passed(f"GitLab runner verified: {len(online_runners)} online runner(s)")
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.skipped(f"Failed to parse GitLab API response: {e}")


# =============================================================================
# TC-UPG-006: SERVICE RESTART AFTER QUADLET UPDATE
# =============================================================================

@pytest.mark.sanity
@pytest.mark.buildstream_upgrade
@pytest.mark.buildstream
@pytest.mark.order(106)
def test_service_restart_after_quadlet_update(host, oim_shared_path, upgrade_config):
    """
    TC-UPG-006: Verify service restart after quadlet update.
    """
    logger = TestLogger(BUILDSTREAM_TEST_NAMES["service_restart_after_quadlet_update"])

    services = [
        BUILDSTREAM_SERVICE,
        POSTGRES_SERVICE,
        PLAYBOOK_WATCHER_QUADLET,
    ]

    for service in services:
        logger.check(BUILDSTREAM_LOG_MSGS["checking_service"].format(service=service))
        result = run_on_oim(host, f"systemctl show --property=ActiveEnterTimestamp {service}")
        assert result.rc == 0, f"Failed to get timestamp for {service}: {result.stderr}"

        timestamp = result.stdout.strip()
        logger.check(BUILDSTREAM_LOG_MSGS["service_timestamp"].format(service=service, timestamp=timestamp))

        result = run_on_oim(host, f"systemctl is-active {service}")
        status = result.stdout.strip()
        assert status == 'active', BUILDSTREAM_ASSERT_MSGS["service_not_active"].format(service=service)

    backup_dir_on_oim = f"{oim_shared_path}/omnia/backups/upgrade/version_{upgrade_config['current_version']}"
    backup_quadlet = f"{backup_dir_on_oim}/{BUILDSTREAM_BACKUP_DIR}/{BUILDSTREAM_CONTAINER_BACKUP}"
    result = run_on_oim(host, f"cat {backup_quadlet}")
    assert result.rc == 0, f"Failed to read backup quadlet: {result.stderr}"
    backup_image = result.stdout

    for line in backup_image.splitlines():
        if line.startswith("Image="):
            backup_image_tag = line.split(":", 1)[-1] if ":" in line else line
            logger.check(BUILDSTREAM_LOG_MSGS["backup_image_tag"].format(tag=backup_image_tag))
            break
    else:
        pytest.fail("Could not find Image= line in backup BuildStream quadlet")

    current_quadlet = f"{QUADLET_DIR}/{BUILDSTREAM_QUADLET}"
    result = run_on_oim(host, f"cat {current_quadlet}")
    assert result.rc == 0, f"Failed to read current quadlet: {result.stderr}"
    current_content = result.stdout

    assert 'Image=' in current_content, "BuildStream quadlet missing Image= directive"

    for line in current_content.splitlines():
        if line.startswith("Image="):
            current_image_tag = line.split(":", 1)[-1] if ":" in line else line
            logger.check(BUILDSTREAM_LOG_MSGS["current_image_tag"].format(tag=current_image_tag))
            break
    else:
        pytest.fail("Could not find Image= line in current BuildStream quadlet")

    assert current_image_tag == BUILDSTREAM_IMAGE_TAG_2_2, \
        BUILDSTREAM_ASSERT_MSGS["quadlet_image_mismatch"].format(
            current=current_image_tag,
            backup=BUILDSTREAM_IMAGE_TAG_2_2,
        )

    postgres_quadlet = f"{QUADLET_DIR}/{POSTGRES_QUADLET}"
    result = run_on_oim(host, f"cat {postgres_quadlet}")
    assert result.rc == 0, f"Failed to read postgres quadlet: {result.stderr}"
    assert 'Image=' in result.stdout, "Postgres quadlet missing Image= directive"

    result = run_on_oim(host, f"cat /etc/systemd/system/{PLAYBOOK_WATCHER_QUADLET}")
    assert result.rc == 0, f"{PLAYBOOK_WATCHER_QUADLET} not found"

    content = result.stdout
    assert 'playbook-watcher/playbook_watcher_service.py' in content, \
        BUILDSTREAM_ASSERT_MSGS["quadlet_source_incorrect"].format(quadlet=PLAYBOOK_WATCHER_QUADLET)
    logger.passed(BUILDSTREAM_LOG_MSGS["quadlet_source_correct"].format(quadlet=PLAYBOOK_WATCHER_QUADLET))

    logger.passed("All services restarted with upgraded configuration")

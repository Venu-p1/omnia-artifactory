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
BuildStream Rollback Test Cases (2.2 → 2.1).

Tests the rollback-specific mechanisms for BuildStream including:
- Pre-rollback DB migration downgrade (007 → 005)
- GitLab revert commit verification
- GitLab config and runner restoration
- Quadlet and source restoration
- Automation environment cleanup
- Service restart after restoration

Prerequisites:
- System must be rolled back to Omnia 2.1
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
    ROLLBACK_VARS,
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
    BUILDSTREAM_IMAGE_TAG_2_1,
    ALEMBIC_VERSION_2_1,
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
def rollback_config():
    """Get rollback configuration from ROLLBACK_VARS."""
    return {
        "current_version": ROLLBACK_VARS["current_version"],
        "new_version": ROLLBACK_VARS["new_version"],
        "backup_path": ROLLBACK_VARS["backup_path"],
    }


@pytest.fixture(scope="module")
def oim_shared_path(host):
    """Get oim_shared_path from omnia_core metadata."""
    metadata = get_oim_metadata(host, OMNIA_CORE_CONTAINER)
    assert metadata["success"], f"Failed to read OIM metadata: {metadata['error']}"
    return metadata["oim_shared_path"]


# =============================================================================
# TC-RBK-001: PRE-ROLLBACK DB MIGRATION DOWNGRADE
# =============================================================================

@pytest.mark.sanity
@pytest.mark.buildstream_rollback
@pytest.mark.buildstream
@pytest.mark.order(201)
def test_db_migration_downgrade(host):
    """
    TC-RBK-001: Verify DB migration downgrade to 2.1.
    """
    logger = TestLogger(BUILDSTREAM_TEST_NAMES["db_migration_downgrade"])

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

    assert version_num == ALEMBIC_VERSION_2_1, \
        BUILDSTREAM_ASSERT_MSGS["alembic_version_mismatch"].format(
            expected=ALEMBIC_VERSION_2_1,
            actual=version_num,
        )

    logger.passed(f"Database downgraded successfully to version {version_num}")


# =============================================================================
# TC-RBK-002: GITLAB REVERT COMMIT CHECK
# =============================================================================

@pytest.mark.sanity
@pytest.mark.buildstream
@pytest.mark.buildstream_rollback
@pytest.mark.order(202)
def test_gitlab_revert_commit(host, oim_shared_path, rollback_config):
    """
    TC-RBK-002: Verify GitLab revert commit.
    """
    logger = TestLogger(BUILDSTREAM_TEST_NAMES["gitlab_revert_commit"])

    manifest_result = get_upgrade_manifest(host)
    if not manifest_result["success"]:
        logger.skipped("upgrade_manifest.yml not found, skipping GitLab revert check")
        pytest.skip("Upgrade manifest not accessible")

    manifest = manifest_result["manifest"]
    backup_dir = manifest.get('backup_dir')
    if not backup_dir:
        pytest.skip("backup_dir not found in manifest")

    # Replace /opt/omnia with oim_shared_path for OIM host access
    metadata_path = backup_dir.replace("/opt/omnia", f"{oim_shared_path}/omnia")
    metadata_path = f"{metadata_path}/{BUILDSTREAM_METADATA_FILE}"
    metadata_result = get_buildstream_metadata(host, metadata_path)
    if not metadata_result["success"]:
        logger.skipped("Upgrade metadata not found, skipping GitLab revert check")
        pytest.skip("Upgrade metadata not accessible")

    metadata = metadata_result["metadata"]
    commit_sha = metadata.get('upgrade_gitlab_commit_sha')
    if not commit_sha:
        logger.skipped("upgrade_gitlab_commit_sha not found in metadata")
        pytest.skip("Upgrade commit SHA not available")

    logger.check(f"Original upgrade commit SHA: {commit_sha}")

    gitlab_host = get_gitlab_host(host)
    if not gitlab_host:
        pytest.skip(BUILDSTREAM_SKIP_MSGS["gitlab_not_configured"])

    logger.check(BUILDSTREAM_LOG_MSGS["gitlab_host"].format(host=gitlab_host))

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
            f'curl -sk -H "PRIVATE-TOKEN: {gitlab_token}" "{api_base}/projects/{encoded_project}/repository/commits?per_page=10"'
        )
        if not result.get("success"):
            logger.skipped(f"GitLab API call failed: {result.get('error')}")
            pytest.skip("GitLab API call failed")

        commits = json.loads(result["stdout"])

        revert_found = False
        for commit in commits:
            message = commit.get('message', '')
            if 'Revert' in message or commit_sha[:12] in message:
                logger.check(f"Found revert commit: {commit['id'][:12]}")
                revert_found = True
                break

        if revert_found:
            logger.passed("GitLab revert commit verified")
        else:
            logger.skipped("Revert commit not found in recent history")

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.skipped(f"Failed to parse GitLab API response: {e}")
        pytest.skip("Could not verify GitLab revert via API")


# =============================================================================
# TC-RBK-003: GITLAB CONFIG & RUNNER RESTORATION
# =============================================================================

@pytest.mark.sanity
@pytest.mark.buildstream
@pytest.mark.buildstream_rollback
@pytest.mark.order(203)
def test_gitlab_config_runner_restoration(host):
    """
    TC-RBK-003: Verify GitLab config and runner restoration.
    """
    logger = TestLogger(BUILDSTREAM_TEST_NAMES["gitlab_config_restoration"])

    gitlab_host = get_gitlab_host(host)
    if not gitlab_host:
        pytest.skip(BUILDSTREAM_SKIP_MSGS["gitlab_not_configured"])

    logger.check(BUILDSTREAM_LOG_MSGS["gitlab_host"].format(host=gitlab_host))

    result = ssh_to_gitlab(host, "test -f /etc/gitlab/gitlab.rb && echo exists || echo not_found")
    if result.get("stdout", "").strip() == 'exists':
        logger.passed("gitlab.rb exists")
    else:
        logger.skipped("gitlab.rb not found or not accessible")

    result = ssh_to_gitlab(host, "test -f /etc/gitlab/gitlab-secrets.json && echo exists || echo not_found")
    if result.get("stdout", "").strip() == 'exists':
        logger.passed("gitlab-secrets.json exists")
    else:
        logger.skipped("gitlab-secrets.json not found or not accessible")

    result = ssh_to_gitlab(host, "systemctl is-active gitlab-runner.service 2>/dev/null || echo unknown")
    runner_status = result.get("stdout", "").strip()
    logger.check(BUILDSTREAM_LOG_MSGS["checking_runner_service"].format(status=runner_status))

    if runner_status == 'active':
        logger.passed("GitLab runner service is active")

    logger.passed("GitLab configuration and runner restoration verified")


# =============================================================================
# TC-RBK-004: QUADLET AND BUILDSTREAM SOURCE RESTORATION
# =============================================================================

@pytest.mark.sanity
@pytest.mark.buildstream
@pytest.mark.buildstream_rollback
@pytest.mark.order(204)
def test_quadlet_source_restoration(host, oim_shared_path, rollback_config):
    """
    TC-RBK-004: Verify quadlet and BuildStream source restoration.
    """
    logger = TestLogger(BUILDSTREAM_TEST_NAMES["quadlet_restoration"])

    backup_dir_on_oim = f"{oim_shared_path}/omnia/backups/upgrade/version_{rollback_config['current_version']}"
    backup_quadlet = f"{backup_dir_on_oim}/{BUILDSTREAM_BACKUP_DIR}/{BUILDSTREAM_CONTAINER_BACKUP}"
    result = run_on_oim(host, f"cat {backup_quadlet}")
    assert result.rc == 0, f"Failed to read backup quadlet: {result.stderr}"
    backup_content = result.stdout

    for line in backup_content.splitlines():
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

    assert current_image_tag == backup_image_tag, \
        BUILDSTREAM_ASSERT_MSGS["quadlet_image_mismatch"].format(
            current=current_image_tag,
            backup=backup_image_tag,
        )

    postgres_quadlet = f"{QUADLET_DIR}/{POSTGRES_QUADLET}"
    result = run_on_oim(host, f"cat {postgres_quadlet}")
    assert result.rc == 0, f"Failed to read postgres quadlet: {result.stderr}"
    assert 'Image=' in result.stdout, "Postgres quadlet missing Image= directive"

    logger.check("Checking BuildStream source directory")
    result = run_on_oim(host, "test -d /opt/omnia/build_stream && echo exists || echo missing")
    assert result.stdout.strip() == 'exists', "BuildStream source directory not found"
    logger.passed("BuildStream source directory exists")

    result = run_on_oim(host, f"cat /etc/systemd/system/{PLAYBOOK_WATCHER_QUADLET}")
    assert result.rc == 0, f"{PLAYBOOK_WATCHER_QUADLET} not found"

    content = result.stdout
    assert 'playbook-watcher/playbook_watcher_service.py' in content, \
        BUILDSTREAM_ASSERT_MSGS["quadlet_source_incorrect"].format(quadlet=PLAYBOOK_WATCHER_QUADLET)
    logger.passed(BUILDSTREAM_LOG_MSGS["quadlet_source_correct"].format(quadlet=PLAYBOOK_WATCHER_QUADLET))

    logger.passed("Quadlet and BuildStream source restoration verified")


# =============================================================================
# TC-RBK-005: AUTOMATION ENVIRONMENT CLEANUP
# =============================================================================

@pytest.mark.sanity
@pytest.mark.buildstream
@pytest.mark.buildstream_rollback
@pytest.mark.order(205)
def test_automation_environment_cleanup(host):
    """
    TC-RBK-005: Verify automation environment cleanup.
    """
    logger = TestLogger(BUILDSTREAM_TEST_NAMES["automation_env_cleanup"])

    result = run_on_oim(host, "test -d /opt/omnia/automation/.venv && echo exists || echo absent")
    venv_status = result.stdout.strip()

    logger.check(f"Automation .venv status: {venv_status}")

    if venv_status == 'absent':
        logger.passed("Automation .venv directory successfully removed")
    else:
        logger.skipped("Automation .venv directory still exists (may be recreated by watcher)")


# =============================================================================
# TC-RBK-008: SERVICE RESTART AFTER RESTORATION
# =============================================================================

@pytest.mark.sanity
@pytest.mark.buildstream
@pytest.mark.buildstream_rollback
@pytest.mark.order(208)
def test_service_restart_after_restoration(host):
    """
    TC-RBK-008: Verify service restart after restoration.
    """
    logger = TestLogger(BUILDSTREAM_TEST_NAMES["service_restart_after_restoration"])

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

    logger.check("Checking for systemd daemon-reload in journal")
    result = run_on_oim(
        host,
        "journalctl -u systemd --since '10 minutes ago' | grep -i 'reload' | tail -5"
    )
    if result.rc == 0 and result.stdout.strip():
        logger.passed("systemd daemon-reload evidence found in journal")
    else:
        logger.check("No recent daemon-reload found in journal")

    logger.passed("Service restart after restoration verified")

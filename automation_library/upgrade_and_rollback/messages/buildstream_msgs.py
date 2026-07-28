# Copyright 2026 Dell Inc. or its subsidiaries. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
BuildStream Module - Messages.

Test names, log messages, assertion messages, and skip messages for
BuildStream upgrade/rollback verification.
"""

from typing import Dict

# =============================================================================
# TEST NAMES — displayed in reports and TestLogger
# =============================================================================

TEST_NAMES: Dict[str, str] = {
    "upgrade_metadata_creation": "Upgrade Metadata Creation",
    "upgrade_backup_validation": "Upgrade Backup Validation",
    "postgres_alembic_migration": "Postgres DB Alembic Migration",
    "gitlab_upgrade_commit": "GitLab Upgrade Commit Verification",
    "gitlab_runner_reregistration": "GitLab Runner Re-registration Check",
    "service_restart_after_quadlet_update": "Service Restart After Quadlet Update",
    "db_migration_downgrade": "Pre-Rollback DB Migration Downgrade",
    "gitlab_revert_commit": "GitLab Revert Commit Verification",
    "gitlab_config_restoration": "GitLab Config Restoration",
    "gitlab_runner_restoration": "GitLab Runner Restoration",
    "quadlet_restoration": "Quadlet and Source Restoration",
    "automation_env_cleanup": "Automation Environment Cleanup",
    "service_restart_after_restoration": "Service Restart After Restoration",
}

# =============================================================================
# LOG MESSAGES — for TestLogger during test execution
# =============================================================================

TEST_LOG_MSGS: Dict[str, str] = {
    "reading_manifest": "Reading upgrade_manifest.yml from {path}",
    "backup_dir": "Backup directory: {path}",
    "checking_metadata": "Checking for metadata file: {path}",
    "metadata_content": "Metadata content: {metadata}",
    "checking_backup_file": "Checking for backup file: {path}",
    "backup_file_missing": "Backup file missing: {path}",
    "backup_dir_on_oim": "Backup directory on OIM: {path}",
    "sql_backup_empty": "SQL backup file exists but is empty (DB may have been empty during backup)",
    "sql_backup_nonempty": "SQL backup file is non-empty",
    "checking_alembic_version": "Checking Alembic version in {table}",
    "current_alembic_version": "Current alembic version: {version}",
    "expected_version": "Expected version: {version}",
    "actual_version": "Actual version: {version}",
    "gitlab_host": "GitLab host: {host}",
    "gitlab_project": "GitLab project: {project}",
    "gitlab_port": "GitLab HTTPS port: {port}",
    "checking_commit": "Checking for upgrade commit with SHA: {sha}",
    "commit_found": "Commit found with title: {title}",
    "commit_not_found": "Commit not found in recent history",
    "checking_runner_service": "GitLab runner service status: {status}",
    "found_runners": "Found {count} runner(s), {online} online",
    "checking_service": "Checking service: {service}",
    "service_timestamp": "{service}: {timestamp}",
    "backup_image_tag": "Backup BuildStream image tag: {tag}",
    "current_image_tag": "Current BuildStream image tag: {tag}",
    "quadlet_source_correct": "{quadlet} points to correct source path",
    "checking_gitlab_config": "Checking GitLab config file: {path}",
    "checking_runner_config": "Checking GitLab runner config.toml",
    "checking_automation_env": "Checking automation environment",
    "automation_env_clean": "Automation environment cleaned up",
}

# =============================================================================
# ASSERTION MESSAGES — shown when tests fail (include HOW TO FIX)
# =============================================================================

TEST_ASSERT_MSGS: Dict[str, str] = {
    "backup_dir_missing": (
        "backup_dir not found in upgrade_manifest.yml\n\n"
        "HOW TO FIX:\n"
        "  1. Check if upgrade was executed successfully\n"
        "  2. Verify upgrade_manifest.yml exists at /opt/omnia/.data/\n"
        "  3. Check upgrade playbook logs for errors"
    ),
    "metadata_file_not_found": (
        "Metadata file not found: {path}\n\n"
        "HOW TO FIX:\n"
        "  1. Verify upgrade completed successfully\n"
        "  2. Check backup directory exists\n"
        "  3. Review upgrade playbook execution logs"
    ),
    "metadata_field_missing": (
        "Required field '{field}' missing from metadata\n\n"
        "HOW TO FIX:\n"
        "  1. Check upgrade playbook metadata creation logic\n"
        "  2. Verify upgrade_build_stream role executed correctly"
    ),
    "metadata_field_empty": (
        "Field '{field}' is empty\n\n"
        "HOW TO FIX:\n"
        "  1. Check upgrade playbook metadata creation logic\n"
        "  2. Verify all required data was captured during upgrade"
    ),
    "upgrade_path_invalid": (
        "Expected upgrade_path='upgrade_existing', got '{actual}'\n\n"
        "HOW TO FIX:\n"
        "  1. Verify this is an upgrade_existing scenario (not fresh install)\n"
        "  2. Check upgrade metadata creation logic"
    ),
    "backup_files_missing": (
        "Missing backup files: {files}\n\n"
        "HOW TO FIX:\n"
        "  1. Verify upgrade backup step completed successfully\n"
        "  2. Check backup directory: {backup_dir}\n"
        "  3. Review upgrade playbook backup tasks"
    ),
    "alembic_version_mismatch": (
        "Expected alembic version {expected}, got {actual}\n\n"
        "HOW TO FIX:\n"
        "  1. Verify database migration completed successfully\n"
        "  2. Check upgrade playbook migration tasks\n"
        "  3. Manually verify: podman exec omnia_postgres psql -U postgres -d buildstream -c 'SELECT version_num FROM alembic_version;'"
    ),
    "gitlab_commit_not_found": (
        "GitLab upgrade commit not found\n\n"
        "HOW TO FIX:\n"
        "  1. Verify GitLab commit was created during upgrade\n"
        "  2. Check upgrade playbook GitLab tasks\n"
        "  3. Manually verify: curl -H 'PRIVATE-TOKEN: <token>' https://{host}/api/v4/projects/{project}/repository/commits"
    ),
    "gitlab_runner_not_active": (
        "GitLab runner service is not active\n\n"
        "HOW TO FIX:\n"
        "  1. Check GitLab runner service status: systemctl status gitlab-runner\n"
        "  2. Restart runner if needed: systemctl restart gitlab-runner\n"
        "  3. Verify runner is registered in GitLab"
    ),
    "gitlab_runner_offline": (
        "GitLab runner is offline\n\n"
        "HOW TO FIX:\n"
        "  1. Check runner connectivity to GitLab server\n"
        "  2. Verify runner configuration in /etc/gitlab-runner/config.toml\n"
        "  3. Restart runner: systemctl restart gitlab-runner"
    ),
    "service_not_active": (
        "Service {service} is not active\n\n"
        "HOW TO FIX:\n"
        "  1. Check service status: systemctl status {service}\n"
        "  2. Check service logs: journalctl -u {service}\n"
        "  3. Restart service if needed"
    ),
    "quadlet_image_mismatch": (
        "BuildStream quadlet image tag does not match backup: current={current}, backup={backup}\n\n"
        "HOW TO FIX:\n"
        "  1. For upgrade: Ensure quadlet was updated to new image tag\n"
        "  2. For rollback: Ensure quadlet was restored to backup image tag\n"
        "  3. Check quadlet file: cat /etc/containers/systemd/omnia_build_stream.container"
    ),
    "quadlet_source_incorrect": (
        "{quadlet} does not point to correct source path\n\n"
        "HOW TO FIX:\n"
        "  1. Verify quadlet file was updated/restored correctly\n"
        "  2. Check quadlet file: cat /etc/containers/systemd/{quadlet}\n"
        "  3. Re-run upgrade/rollback if needed"
    ),
    "gitlab_config_missing": (
        "GitLab config file not found: {path}\n\n"
        "HOW TO FIX:\n"
        "  1. Verify GitLab config was backed up during upgrade\n"
        "  2. Check backup directory for config files\n"
        "  3. Restore config from backup if missing"
    ),
    "automation_env_not_clean": (
        "Automation environment not cleaned up\n\n"
        "HOW TO FIX:\n"
        "  1. Verify rollback cleanup tasks executed\n"
        "  2. Check for leftover files/directories\n"
        "  3. Manually clean up if needed"
    ),
}

# =============================================================================
# SKIP MESSAGES — for pytest.skip() calls
# =============================================================================

SKIP_MSGS: Dict[str, str] = {
    "backup_file_missing": "Backup file missing: {path}",
    "sql_backup_empty": "SQL backup file is empty (DB may have been empty during backup)",
    "gitlab_not_configured": "GitLab not configured in omnia_test_config.yml",
    "gitlab_host_not_reachable": "GitLab host not reachable: {host}",
    "gitlab_token_missing": "GitLab root token not found",
    "buildstream_not_enabled": "BuildStream not enabled in software_config.json",
}
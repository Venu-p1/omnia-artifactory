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
BuildStream Module - Variables.

Path constants and configuration for BuildStream upgrade/rollback verification.
"""

from typing import Dict, Any

from ...core import (
    OMNIA_CORE_CONTAINER,
)

# =============================================================================
# PATH CONSTANTS (inside omnia_core container)
# =============================================================================

UPGRADE_MANIFEST_PATH: str = "/opt/omnia/.data/upgrade_manifest.yml"
OIM_DATA_PATH: str = "/opt/omnia/.data"
BUILDSTREAM_BACKUP_DIR: str = "buildstream"
BUILDSTREAM_METADATA_FILE: str = "buildstream_upgrade_metadata.yml"
GITLAB_CONFIGS_DIR: str = "configs/gitlab"

# BuildStream-specific backup files
BUILDSTREAM_CONTAINER_BACKUP: str = "omnia_build_stream.container.bak"
POSTGRES_CONTAINER_BACKUP: str = "omnia_postgres.container.bak"
BUILDSTREAM_DB_BACKUP: str = "buildstream_db_backup.sql"
GITLAB_RB_BACKUP: str = "gitlab.rb"
GITLAB_SECRETS_BACKUP: str = "gitlab-secrets.json"

# Quadlet paths (on OIM host)
QUADLET_DIR: str = "/etc/containers/systemd"
BUILDSTREAM_QUADLET: str = "omnia_build_stream.container"
BUILDSTREAM_SERVICE: str = "omnia_build_stream.service"
POSTGRES_QUADLET: str = "omnia_postgres.container"
POSTGRES_SERVICE: str = "omnia_postgres.service"
PLAYBOOK_WATCHER_QUADLET: str = "playbook_watcher.service"

# Quadlet image tags (version-specific)
BUILDSTREAM_IMAGE_TAG_2_1: str = "1.0"
BUILDSTREAM_IMAGE_TAG_2_2: str = "1.1"

# Alembic migration versions
ALEMBIC_VERSION_2_1: str = "005"
ALEMBIC_VERSION_2_2: str = "007"

# GitLab API constants
GITLAB_API_BASE: str = "/api/v4"
GITLAB_COMMIT_TITLE_PREFIX: str = "[omnia-upgrade-2.1-to-2.2]"
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
BuildStream Module - Functions.

Helper functions for BuildStream upgrade/rollback verification.
"""

from typing import Dict, Any

from ...core import (
    run_in_container,
    run_on_oim,
    OMNIA_CORE_CONTAINER,
)
from ..vars.buildstream_vars import (
    UPGRADE_MANIFEST_PATH,
)


def read_container_file(host, path: str) -> Dict[str, Any]:
    """
    Read a file from inside the omnia_core container.

    Args:
        host: Testinfra host object
        path: Path to file inside container

    Returns:
        Dict containing:
            - success (bool): True if file read successfully
            - content (str): File content
            - error (str): Error message if failed
    """
    result = run_in_container(host, f"cat {path}", container=OMNIA_CORE_CONTAINER)
    if result.rc != 0:
        return {
            "success": False,
            "content": "",
            "error": f"Failed to read {path}: {result.stderr}",
        }
    return {
        "success": True,
        "content": result.stdout,
        "error": "",
    }


def read_oim_file(host, path: str) -> Dict[str, Any]:
    """
    Read a file from the OIM host.

    Args:
        host: Testinfra host object
        path: Path to file on OIM host

    Returns:
        Dict containing:
            - success (bool): True if file read successfully
            - content (str): File content
            - error (str): Error message if failed
    """
    result = run_on_oim(host, f"cat {path}")
    if result.rc != 0:
        return {
            "success": False,
            "content": "",
            "error": f"Failed to read {path}: {result.stderr}",
        }
    return {
        "success": True,
        "content": result.stdout,
        "error": "",
    }


def get_gitlab_root_token(host, ssh_to_gitlab_func, token_file_path: str) -> Dict[str, Any]:
    """
    Read GitLab root token from the GitLab server.

    Args:
        host: Testinfra host object
        ssh_to_gitlab_func: Function to SSH to GitLab server
        token_file_path: Path to token file on GitLab server

    Returns:
        Dict containing:
            - success (bool): True if token read successfully
            - token (str): GitLab root token
            - error (str): Error message if failed
    """
    result = ssh_to_gitlab_func(host, f"cat {token_file_path}")
    if result.get("success"):
        return {
            "success": True,
            "token": result["stdout"].strip(),
            "error": "",
        }
    return {
        "success": False,
        "token": "",
        "error": result.get("error", "Failed to read GitLab token"),
    }


def get_upgrade_manifest(host) -> Dict[str, Any]:
    """
    Read upgrade manifest from container.

    Args:
        host: Testinfra host object

    Returns:
        Dict containing:
            - success (bool): True if manifest read successfully
            - manifest (dict): Parsed YAML manifest
            - error (str): Error message if failed
    """
    result = read_container_file(host, UPGRADE_MANIFEST_PATH)
    if not result["success"]:
        return {
            "success": False,
            "manifest": {},
            "error": result["error"],
        }

    import yaml
    try:
        manifest = yaml.safe_load(result["content"])
        if not manifest:
            return {
                "success": False,
                "manifest": {},
                "error": "Upgrade manifest is empty",
            }
        return {
            "success": True,
            "manifest": manifest,
            "error": "",
        }
    except yaml.YAMLError as e:
        return {
            "success": False,
            "manifest": {},
            "error": f"Failed to parse YAML: {str(e)}",
        }


def get_buildstream_metadata(host, metadata_path: str) -> Dict[str, Any]:
    """
    Read BuildStream upgrade metadata from backup directory.

    Args:
        host: Testinfra host object
        metadata_path: Full path to buildstream_upgrade_metadata.yml

    Returns:
        Dict containing:
            - success (bool): True if metadata read successfully
            - metadata (dict): Parsed YAML metadata
            - error (str): Error message if failed
    """
    result = read_oim_file(host, metadata_path)
    if not result["success"]:
        return {
            "success": False,
            "metadata": {},
            "error": result["error"],
        }

    import yaml
    try:
        metadata = yaml.safe_load(result["content"])
        if not metadata:
            return {
                "success": False,
                "metadata": {},
                "error": "BuildStream metadata is empty",
            }
        return {
            "success": True,
            "metadata": metadata,
            "error": "",
        }
    except yaml.YAMLError as e:
        return {
            "success": False,
            "metadata": {},
            "error": f"Failed to parse YAML: {str(e)}",
        }
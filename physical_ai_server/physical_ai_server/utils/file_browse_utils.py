#!/usr/bin/env python3
#
# Copyright 2025 ROBOTIS CO., LTD.
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
#
# Author: Kiwoong Park


"""File browser utility class for handling file system operations."""

import os
import datetime


class FileBrowseUtils:
    """Utility class for file browsing operations."""

    def __init__(self):
        """Initialize the FileBrowseUtils instance."""
        pass

    def handle_get_path_action(self, current_path):
        """Handle get_path action and return path information."""
        current_path = current_path or os.path.expanduser("~")
        current_path = os.path.abspath(current_path)

        return {
            'success': True,
            'message': "Current path retrieved successfully",
            'current_path': current_path,
            'parent_path': os.path.dirname(current_path),
            'selected_path': "",
            'items': []
        }

    def handle_go_parent_action(self, current_path):
        """Handle go_parent action and return parent directory information."""
        current_path = current_path or os.path.expanduser("~")
        parent_path = os.path.dirname(os.path.abspath(current_path))

        if os.path.exists(parent_path) and os.path.isdir(parent_path):
            return {
                'success': True,
                'message': "Navigated to parent directory",
                'current_path': parent_path,
                'parent_path': os.path.dirname(parent_path),
                'selected_path': "",
                'items': self._get_directory_items(parent_path)
            }
        else:
            return {
                'success': False,
                'message': "Cannot navigate to parent directory",
                'current_path': current_path,
                'parent_path': "",
                'selected_path': "",
                'items': []
            }

    def handle_browse_action(self, current_path, target_name=None):
        """Handle browse action for directory or file selection."""
        current_path = current_path or os.path.expanduser("~")
        current_path = os.path.abspath(current_path)

        if target_name:
            return self._handle_target_selection(current_path, target_name)
        else:
            return self._handle_directory_browse(current_path)

    def _handle_target_selection(self, current_path, target_name):
        """Handle target file/directory selection."""
        target_path = os.path.join(current_path, target_name)

        if os.path.exists(target_path):
            if os.path.isdir(target_path):
                # Navigate into directory
                return {
                    'success': True,
                    'message': f"Navigated to {target_name}",
                    'current_path': target_path,
                    'parent_path': current_path,
                    'selected_path': target_path,
                    'items': self._get_directory_items(target_path)
                }
            else:
                # Select file
                return {
                    'success': True,
                    'message': f"Selected file {target_name}",
                    'current_path': current_path,
                    'parent_path': os.path.dirname(current_path),
                    'selected_path': target_path,
                    'items': self._get_directory_items(current_path)
                }
        else:
            return {
                'success': False,
                'message': f"Item {target_name} not found",
                'current_path': current_path,
                'parent_path': os.path.dirname(current_path),
                'selected_path': "",
                'items': self._get_directory_items(current_path)
            }

    def _handle_directory_browse(self, current_path):
        """Handle directory browsing."""
        if os.path.exists(current_path) and os.path.isdir(current_path):
            return {
                'success': True,
                'message': "Directory browsed successfully",
                'current_path': current_path,
                'parent_path': os.path.dirname(current_path),
                'selected_path': "",
                'items': self._get_directory_items(current_path)
            }
        else:
            # Return error if directory doesn't exist
            return {
                'success': False,
                'message': f"Directory does not exist: {current_path}",
                'current_path': "",
                'parent_path': "",
                'selected_path': "",
                'items': []
            }

    def _get_directory_items(self, directory_path):
        """Get list of items in the directory as dictionaries."""
        items = []

        try:
            if (not os.path.exists(directory_path) or
                    not os.path.isdir(directory_path)):
                return items

            for item_name in sorted(os.listdir(directory_path)):
                # Skip hidden files and directories
                if item_name.startswith('.'):
                    continue

                item_path = os.path.join(directory_path, item_name)

                try:
                    is_directory = os.path.isdir(item_path)

                    if is_directory:
                        size = -1  # Directory size set to -1
                    else:
                        size = os.path.getsize(item_path)

                    # Get modification time
                    mtime = os.path.getmtime(item_path)
                    timestamp = datetime.datetime.fromtimestamp(mtime)
                    modified_time = timestamp.strftime('%Y-%m-%d %H:%M:%S')

                    item_dict = {
                        'name': item_name,
                        'full_path': item_path,
                        'is_directory': is_directory,
                        'size': size,
                        'modified_time': modified_time
                    }

                    items.append(item_dict)

                except (OSError, PermissionError):
                    # Skip items that can't be accessed
                    continue

        except (OSError, PermissionError):
            # Return empty list if directory can't be read
            pass

        return items

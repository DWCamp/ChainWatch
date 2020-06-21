"""
FileEvent

@author Daniel Campman
@date 2020-04-12
"""

from enum import Enum


class FileEvent(Enum):
    """
    An enumerated value for each of the types of file events to watch

    Common
    ------
        - ADD: A file was moved into or renamed inside the directory
        - CREATE: File is created inside the directory
        - DELETE: File is deleted from the directory
        - MODIFY: Existing file was changed without being removed
        - OPEN: File is opened and being read
        - REMOVE: The old name after file renamed/moved out (but not deleted)

    Others
    ------
        - CLOSE_NO_WRITE: File is closed without modifying its contents
        - CLOSE_WRITE: File is written to and closed
        - DIR_DELETED: The watched directory was deleted
        - DIR_MOVED: The watched directory was moved
        - IS_DIR: Someone checked if the directory was a directory
        - METADATA: A file's metadata (e.g. owner) was changed, but not its contents
        - READ: A file is being accessed (e.g. executed)
        - UNWATCH: A directory is no longer being watched. Triggered through recursive watching
    """

    ADD = "IN_MOVED_TO"
    CLOSE_WRITE = "IN_CLOSE_WRITE"
    CLOSE_NO_WRITE = "IN_CLOSE_NOWRITE"
    CREATE = "IN_CREATE"
    DIR_DELETED = "IN_DELETE_SELF"
    DELETE = "IN_DELETE"
    DIR_MOVED = "IN_MOVE_SELF"
    IS_DIR = "IN_ISDIR"
    METADATA = "IN_ATTRIB"
    MODIFY = "IN_MODIFY"
    OPEN = "IN_OPEN"
    READ = "IN_ACCESS"
    REMOVE = "IN_MOVED_FROM"
    UNWATCH = "IN_IGNORED"

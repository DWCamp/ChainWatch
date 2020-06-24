#! /usr/bin/python3.7

# First party imports
import argparse
from datetime import datetime
import os
import shutil
# Personal imports
from filewatcher import FileWatcher, FileEvent
import dbconnection
from config import Config

active_link_ids = set()  # The set of link ids which are locked while another thread is processing a different image

CONFIG = None                            # The configuration object
CONFIG_FILE = "config.json"              # The name of the module's configuration file
MODULE_DIR = os.path.split(__file__)[0]  # The directory of this module


def parse_name(file_name: str):
    """
    Parses a filename of the structure

        <NAME>_(GOOD/FAIL/UNKNOWN)_LP-#1_ID-#2.jpg

    Where `<NAME>` is the camera's name (as defined in the config file), `#1` is the loop count,
    and `#2` is the ID count. None of these values should be zero padded

    :param file_name:
    :return: If name is of an invalid format, returns "None". Otherwise, returns a tuple of four values:
        0 : bool
            `True` if the file was "GOOD", `False` if file was "FAIL"
        1 : int
            The loop count
        2 : int
            The ID count
        3 : str
            The name of the camera this photo came from
    """
    import re
    parsed = re.search(r"(\w+)_(\w+)_LP-(\d+)_ID-(\d+)", file_name)
    if parsed is None:  # Reject invalid
        print(f"Couldn't parse file name `{file_name}`")
        return None

    # Check which camera was used
    camera = parsed.group(1)
    if parsed.group(2) == CONFIG['PASS_TAG']:
        passed = True
    elif parsed.group(2) == CONFIG['FAIL_TAG']:
        passed = False
    elif parsed.group(2) == CONFIG['UNKNOWN_TAG']:
        passed = None
    else:
        print(f"Unrecognized inspection result `{parsed.group(2)}`")
        return None
    loop_id = int(parsed.group(3))
    link_id = int(parsed.group(4))
    return passed, loop_id, link_id, camera


def detect_file(data: (FileEvent, str, str)) -> None:
    """
    The target function which gets called when a file is detected
    :param data: A three element tuple containing
        - the inciting FileEvent type
        - the name of the file
        - the name of the folder the file was inside
    """
    (event, name, dir_path) = data

    # Ignore the module directory
    if dir_path == MODULE_DIR:
        return

    # Parse filename
    file_data = parse_name(name)
    if file_data is None:
        return
    (passed, loop_count, link_id, camera) = parse_name(name)
    (root, parent_dir) = os.path.split(dir_path)
    print(f"Found `{name}` from camera `{parent_dir}`")

    # Get current time
    time = datetime.utcnow()

    # Process camera name
    if camera == CONFIG['LEFT_CAMERA']:
        left_camera = True
    elif camera == CONFIG['RIGHT_CAMERA']:
        left_camera = False
    else:
        left_camera = None

    # Rename and move file
    source = f"{dir_path}/{name}"
    filename, file_ext = os.path.splitext(name)
    new_name = f"{filename}_{int(time.timestamp())}{file_ext}"
    dest = f"{CONFIG['IMG_DESTINATION']}/{new_name}"
    shutil.move(source, dest)  # Move the file into the destination folder
    dbconnection.log_image(link_id, loop_count, left_camera, passed, dest)  # Record image to database
    dbconnection.trim_images(link_id, CONFIG['RECENT_IMAGE_LIMIT'], CONFIG['FAIL_IMAGE_LIMIT'])


def load_config() -> None:
    global CONFIG
    required_keys = {
        "LEFT_CAMERA": str,
        "RIGHT_CAMERA": str,
        "FAIL_IMAGE_LIMIT": int,
        "RECENT_IMAGE_LIMIT": int,
        "IMG_DESTINATION": str
    }
    CONFIG = Config(f"{MODULE_DIR}/{CONFIG_FILE}", required_keys=required_keys)
    print("Loaded config file.")


def reload(data: (FileEvent, str, str)) -> None:
    """
    FileWatcher target for reloading script files

    :param data: The data from the FileWatcher
    """
    (event, name, dir_path) = data
    # Ignore anything but the config file in the package directory
    if not dir_path == MODULE_DIR or not name == CONFIG_FILE:
        return
    CONFIG.reload()
    print("Config file reloaded.")


# ==============================================================================================================
# =================================================================================================  MAIN METHOD
# ==============================================================================================================

if __name__ == "__main__":
    # ------ Parse arguments

    parser = argparse.ArgumentParser(description="Library for executing tasks in response to Linux file events")
    parser.add_argument("-R",
                        "--recursive",
                        action="store_true",
                        help="Events will also be triggered for all subdirectories of the one being watched")
    parser.add_argument("-S",
                        "--synchronous",
                        action="store_true",
                        help="Whether to disable threading of targets, causing them to execute synchronously.")
    parser.add_argument("paths", nargs='+', help="The paths of each directory to watch")
    args = parser.parse_args()

    # ------ Load config file

    load_config()

    # ------ Start file watchdog

    # Check that every path requested exists
    for path in args.paths:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Could not locate the directory {path}")

    # Also watch the config directory for changes to the config file
    paths = args.paths
    paths.append(MODULE_DIR)

    # Start and run the watchdog
    watchdog = FileWatcher(args.paths,
                           recursive=args.recursive,
                           threaded_events=args.recursive)               # Create the FileWatcher object
    watchdog.register_target(reload, events=FileEvent.CLOSE_WRITE)       # Reload config file when modified
    watchdog.register_target(detect_file, events=FileEvent.CLOSE_WRITE)  # Watch FTP directory
    print("Starting filewatcher...")
    watchdog.start()                                                     # Begin watching the directory
    dbconnection.close()                                                 # Close database

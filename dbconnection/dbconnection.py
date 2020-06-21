import os
from typing import Optional
import mysql.connector
import mysql.connector.cursor as mysql_cursor
from config import Config

_cnx = None
_last_id = None
_CONFIG_FILE = "config.json"              # The name of the module's configuration file
_MODULE_DIR = os.path.split(__file__)[0]  # The directory of this module
_CONFIG = Config(f"{_MODULE_DIR}/{_CONFIG_FILE}")


def connect() -> mysql_cursor:
    """
    Establishes a connection with the database and returns a cursor

    :raises: mysql.connector.Error if there is a failure to connect
    :return: A cursor for the database. 'None' if failed to connect
    """
    global _cnx
    if _cnx is None:  # Connect to the database
        _cnx = mysql.connector.connect(user=_CONFIG.values['MYSQL_USERNAME'],
                                       password=_CONFIG.values['MYSQL_PASSWORD'],
                                       host=_CONFIG.values['MYSQL_HOST'],
                                       database=_CONFIG.values['MYSQL_DATABASE'],
                                       autocommit=True)
    if not _cnx.is_connected():  # Reconnect to the database if connection was lost
        print("Reconnecting to database...")
        _cnx.reconnect()
    return _cnx.cursor()


def close() -> None:
    """
    Closes the connection to the database
    """
    global _cnx
    if _cnx:
        _cnx.close()
    _cnx = None


# =======================================================================================================
# ===================================    IMAGES TABLE    ================================================
# =======================================================================================================


def log_image(link_id: int, loop: int, left_camera: bool, passed: bool, file_path: str) -> None:
    """
    Adds an entry into the database for a given image
    :param link_id: The link number
    :param loop: The number of loops the chain has made
    :param left_camera: `True` if this image was captured with the left camera, `False` if captured with the right
    :param passed: Whether link passed the inspection (i.e. a 'GOOD' image)
    :param file_path: The path to the file where the image is being stored
    """
    global _last_id
    statement = "INSERT INTO images (link_id, loop_count, left_camera, passed, filepath) VALUES (%(link_id)s, " \
                "%(loop)s, %(left_camera)s, %(passed)s, %(filepath)s)"
    data = {
        'link_id': link_id,
        'loop': loop,
        'left_camera': left_camera,
        'passed': passed,
        'filepath': file_path
    }
    cursor = connect()  # Verify database connection
    _cnx.start_transaction()
    cursor.execute(statement, data)
    _last_id = cursor.lastrowid
    _cnx.commit()


def clear_img_database(link_id: int = None) -> None:
    """
    Removes all images from the database for one link.
    If no link is specified, all images are removed

    :param link_id: Specifies a single link to be removed
    """
    if link_id:
        statement = f"DELETE FROM images WHERE link_id={link_id}"
    else:
        statement = "DELETE FROM images"
    cursor = connect()
    _cnx.start_transaction()
    cursor.execute(statement)
    _cnx.commit()


def count_at_risk(threshold: float) -> int:
    """
    Counts the links that are "at risk" (i.e. have a dangerously low pass rate)
    :param threshold: The pass rate at or below which a link is considered "at risk"
    :return: The number of links below the threshold
    """
    pass_rates = get_pass_rates()     # Get the pass rates for each link
    count = 0
    for rate in pass_rates.values():  # Count the links below the pass rate threshold
        if rate <= threshold:
            count += 1
    return count


def count_images() -> int:
    """
    Counts the images
    :return: The number of entries in the database
    """
    statement = "SELECT COUNT(*) FROM images"
    cursor = connect()
    cursor.execute(statement)
    return cursor.fetchone()[0]


def count_links() -> int:
    """
    Counts the links
    :return: The number of links in the database
    """
    statement = "SELECT COUNT(DISTINCT(link_id)) FROM images"
    cursor = connect()
    cursor.execute(statement)
    return cursor.fetchone()[0]


def fetch_link(link_id: int) -> dict:
    """
    Fetches the details on a given link from the database
    :param link_id: The id of the link being checked
    :return: A dictionary containing the details of a given link. The dictionary contains the following items:
        "image_list" : list
            The list of recent images from both cameras
        "past_failures" : list
            A list of images that failed inspection that fell off the end of the camera lists
    """
    img_statement = "SELECT * FROM images WHERE link_id = %(link_id)s ORDER BY img_id DESC"
    data = {"link_id": link_id}
    cursor = connect()  # Verify database connection
    cursor.execute(img_statement, data)

    # Compile list of images
    image_list = [dict(zip(cursor.column_names, image)) for image in cursor]

    pf_statement = "SELECT * FROM past_failures WHERE link_id = %(link_id)s ORDER BY img_id DESC"
    cursor = connect()  # Create a second cursor
    cursor.execute(pf_statement, data)

    # Compile list of past failures with column names
    failure_list = [dict(zip(cursor.column_names, image)) for image in cursor]

    return {
        "image_list": image_list,
        "past_failures": failure_list
    }


def find_worst_links(limit: int = 5) -> list:
    """
    Ranks the links by pass rate and returns a list of the N lowest
    :param limit: The number of links to find
    :return: A list of tuples, containing the link ids and their pass rates.
    """
    statement = ("SELECT link_id, SUM(passed)/COUNT(*) pass_rate "
                 "FROM images "
                 "GROUP BY link_id "
                 "ORDER BY pass_rate ASC "
                 f"LIMIT {max(limit, 0)}")  # Prevent negative values from crashing the request
    cursor = connect()
    cursor.execute(statement)
    links = cursor.fetchall()
    # Return empty list if database was empty
    result = [(link[0], float(link[1])) for link in links] if links else []
    return result


def get_most_recent_image() -> Optional[dict]:
    """
    Fetches the record for the most recently added image and returns the
    details of the image
    :return: A dictionary containing the value of each column in the most recent
        image record. Returns "None" if there are no images in the database
    """
    cursor = connect()
    if _last_id:  # If cursor has last row ID, it removes the need for a query
        statement = f"SELECT * FROM images WHERE img_id = {_last_id}"
    else:
        statement = "SELECT * FROM images WHERE img_id = (SELECT MAX(img_id) FROM images)"
    cursor.execute(statement)
    top_result = cursor.fetchone()
    if top_result:  # Only return a dictionary if there is a result
        return dict(zip(cursor.column_names, top_result))


def get_pass_rates() -> dict:
    """
    Returns the pass rates for every link in a dictionary, where the keys are the ids of each link
    :return: [int: float] A dictionary of each link's pass rate, with the link's id as the key
    """
    statement = "SELECT link_id, SUM(`passed`) passes, COUNT(*) images FROM images GROUP BY link_id"
    cursor = connect()
    cursor.execute(statement)
    results = {}
    for (link_id, passes, images) in cursor:
        results[link_id] = float(passes/images)
    return results


def trim_images(link: int, keep_recent: int, keep_failures: int) -> None:
    """
    Removes excess images from the database.

    :param link: The id of the link
    :param keep_recent: The number of recent images to keep
    :param keep_failures: The number of past failures to keep
    """
    # These queries are as horrifying to read as they were for me to write. I'm sorry.
    transfer_statement = ("INSERT INTO past_failures "
                          "SELECT * FROM images "
                          "WHERE NOT passed AND "
                          "img_id IN (SELECT * FROM ("
                          "SELECT img_id FROM images "
                          "WHERE link_id = %(link_id)s "
                          "ORDER BY img_id DESC "
                          "LIMIT 1000 OFFSET %(offset)s) temp )")

    remove_images = ("DELETE FROM images WHERE link_id = %(link_id)s AND img_id <= "
                     "(SELECT img_id FROM images "
                     "WHERE link_id = %(link_id)s "
                     "ORDER BY img_id DESC "
                     "LIMIT 1 OFFSET %(offset)s)")
    remove_failures = ("DELETE FROM past_failures WHERE link_id = %(link_id)s AND img_id <= "
                       "(SELECT img_id FROM past_failures "
                       "WHERE link_id = %(link_id)s "
                       "ORDER BY img_id DESC "
                       "LIMIT 1 OFFSET %(offset)s)")
    cursor = connect()
    _cnx.start_transaction()

    """ Transfer overflow failures from images to past_failures """
    data = {
        "link_id": link,
        "offset": keep_recent
    }
    cursor.execute(transfer_statement, data)

    """ Remove old images from both tables """
    data = {
        "link_id": link,
        "offset": keep_recent
    }
    cursor.execute(remove_images, data)
    data = {
        "link_id": link,
        "offset": keep_failures
    }
    cursor.execute(remove_failures, data)

    """ Commit transaction """
    _cnx.commit()


# =======================================================================================================
# ===================================    CONFIG TABLE    ================================================
# =======================================================================================================


def get_attribute(attribute: str) -> Optional[str]:
    """
    Fetches an attribute from the configuration table

    :param attribute: The key/name for the value
    :raises ValueError: If the attribute does not exist in the table
    :return: The value of the attribute
    """
    update_statement = "SELECT value FROM config WHERE attribute = %(attribute)s"
    data = {
        'attribute': attribute,
    }
    cursor = connect()
    cursor.execute(update_statement, data)
    result = cursor.fetchone()
    if result is None:
        raise ValueError(f"No attribute {attribute} in configuration table")
    return result[0]


def set_attribute(attribute: str, value, no_insert: bool = False) -> None:
    """
    Updates the value of an attribute in the configuration database.
    If this attribute did not previously exist, it will be inserted into the table,
    unless `no_insert` is set to `False`. If so, a ValueError exception will be thrown

    If value is not `None`, it will be cast to `str` before being stored in the table

    :param attribute: The key/name for the value
    :param value: The value of the attribute
    :param no_insert: If `True`, an exception will be thrown if `attribute` does not match an
        existing entry in the table. Otherwise, the new attribute will be inserted
    :raises ValueError: If no_insert is `True` and the attribute does not exist in the table
    """
    update_statement = "UPDATE config SET value = %(value)s WHERE attribute = %(attribute)s"
    data = {
        'attribute': attribute,
        'value': str(value) if value is not None else None  # Cast non-None values to string
    }
    cursor = connect()
    _cnx.start_transaction()
    cursor.execute(update_statement, data)
    if cursor.rowcount == 0:  # If attribute was not in table, insert if allowed
        if no_insert:
            raise ValueError(f"No attribute {attribute} in configuration table")
        insert_statement = f"INSERT INTO config VALUES (%(attribute)s, %(value)s)"
        cursor.execute(insert_statement, data)
    _cnx.commit()

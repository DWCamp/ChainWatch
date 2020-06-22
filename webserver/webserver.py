"""
Web Server v0.1

This is a web server for rendering the current
status of the links in the chain

@author Daniel Campman
@date 4/11/2020
"""

from datetime import datetime, timedelta
import importlib
import json
import os
from typing import Optional

from flask import Flask
from flask import jsonify, redirect, render_template, request, send_from_directory, url_for
import qrcode

from dbconnection import dbconnection
from config import Config

app = Flask(__name__)
HOSTNAME = '0.0.0.0'  # The hostname for external access
PORT = None

CONFIG = None                            # The configuration object
CONFIG_FILE = "config.json"              # The name of the module's configuration file
MODULE_DIR = os.path.split(__file__)[0]  # The directory of this module

# The list of web pages to appear in the navbar, including their navbar title and URL
nav_list = [
    {
        'page': 'Home',
        'location': '/'
    },
    {
        'page': 'Status Grid',
        'location': '/grid'
    },
    {
        'page': 'Configure',
        'location': '/configure'
    },
    {
        'page': 'Documentation',
        'location': '/spec'
    },
]


# =============================================================================================
# ==================================    HELPER METHODS    =====================================
# =============================================================================================


def create_qr():
    # Unfortunately, this is the only way to reliably get the current IP address on a Debian system
    stream = os.popen('hostname -I')  # Run Linux on
    ip_addr = stream.read().strip()
    qr_img = qrcode.make(f"http://{ip_addr}:{PORT}")
    qr_img.save(os.path.join(app.root_path, 'static/qr_code.jpg'))


def error_code(message):
    """
    Returns a jsonify response with a given error message
    :param message: The message to include in the error response
    :return: The jsonify response
    """
    return jsonify({
        "status": "error",
        "code": 400,
        "data": {
            "message": message
        }
    }), 400


def json_to_list(config: dict) -> list:
    """
    Converts a JSON dictionary of config values to a list of dictionaries,
    where each element contains the following keys:
        - name: (str) The name of the attribute
        - type: (str) The type of the input field this value should have (number or text)
        - value: (str/int) The value of the attribute
        - comment: (Optional[str]) The comment for the attribute if present, else None

    :param config: The JSON dictionary to convert
    :return: The list of dictionaries
    """
    attr_list = []
    for attribute in config:
        if not attribute.startswith("_"):
            comment_key = "_comment_" + attribute
            attr_list.append({
                "name": attribute,
                "type": "number" if type(config[attribute]) is int else "text",
                "value": config[attribute],
                "comment": config[comment_key] if comment_key in config else None
            })
    return attr_list


def load_config():
    global CONFIG

    """ The keys which must be defined in the configuration file """
    required_keys = {
        "SPEC_FILENAME": str,
        "MEDIA_FOLDER": str,
        "PORT": int,
        "ACTIVE_DELAY": int,
        "NUM_WORST": int,
        "WARNING_THRESHOLD": float,
    }
    CONFIG = Config(f"{MODULE_DIR}/{CONFIG_FILE}", required_keys=required_keys)


def package_to_config(package: str) -> Optional[str]:
    """
    Looks up the name of a module and returns the path to
    its root level config.json file. If the package or file
    does not exist, `None` is returned

    :param package: The name of a python package
    :return: The absolute path to its configuration file.
        `None` if package does not exist or the package does
        not have a root level `config.json` file
    """
    spec = importlib.util.find_spec(package)
    if spec is None:  # Check if package exists
        return None
    package_path = spec.origin
    file = f"{os.path.split(package_path)[0]}/config.json"
    # Return file if it exists. Otherwise `None` is returned implicitly
    if os.path.exists(file):
        return file


# =============================================================================================
# =====================================    WEB PAGES    =======================================
# =============================================================================================

# ----------------------- Navigation Bar items

@app.route('/')
def index():
    """
    The homepage for the website. Provides an overview of the system as well
    as a QR code for viewing the website
    """
    overview = {}

    # The number of links
    link_count = dbconnection.count_links()
    overview['link_count'] = link_count
    overview['image_count'] = dbconnection.count_images()

    """ Check the chain status """
    if link_count == 0:  # Create default dictionary if database is empty
        overview['most_recent'] = {
            'img_id': 0,
            'link_id': 'N/A',
            'loop_count': 'N/A',
            'time': 'N/A'
        }
        overview['active'] = False
        overview['offline_dur'] = 'N/A'
    else:
        overview['most_recent'] = dbconnection.get_most_recent_image()

        # See if line is active, i.e. has inspected a chain within a given time frame
        # If inactive, calculate create a string representing the time the system has been offline
        time_elapsed = datetime.utcnow() - overview['most_recent']['time']
        overview['active'] = time_elapsed < timedelta(seconds=CONFIG['ACTIVE_DELAY'])
        if not overview['active']:
            hours, remainder = divmod(time_elapsed.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            overview['offline_dur'] = "%02dh %02dm %02ds" % (hours, minutes, seconds)

    """ List the links with the worst pass rate """
    worst_links = dbconnection.find_worst_links(CONFIG['NUM_WORST'])
    worst_link_list = []
    for link in worst_links:
        link_dict = {
            "link_id": link[0],
            "pass_rate": "%.2f%%" % (link[1] * 100)  # Convert ratio to string with percentage
        }
        worst_link_list.append(link_dict)
    overview['worst'] = worst_link_list

    """ Calculate the number/percentage of links whose pass rate is below a certain threshold """
    if link_count == 0:
        overview['at_risk_str'] = "N/A"
    else:
        at_risk_count = dbconnection.count_at_risk(threshold=CONFIG['WARNING_THRESHOLD'])
        risk_perc = round(100 * at_risk_count / link_count, 2)
        overview['at_risk_str'] = f"{at_risk_count} ({risk_perc}%)"

    return render_template('index.html', curr_page='Home', nav_list=nav_list, title="Home", overview=overview)


@app.route('/grid')
def grid():
    """
    A page displaying all of the links in a large grid, color coded based on their failure rates
    """
    title = "List of links in collection"
    link_list = []
    for link_id, pass_rate in dbconnection.get_pass_rates().items():
        weighted_pass_rate = pass_rate ** 2                   # Adjust pass_rate to inflate lower scores
        blue_val = int(255 * weighted_pass_rate)              # Calculate blue component of color
        red_val = int(255 * (1 - weighted_pass_rate))         # Calculate red component of color
        hex_string = "#%0.6X" % ((red_val << 16) + blue_val)  # Convert to hex color code
        link_data = {
            "style": f"background-color: {hex_string}; color: white",
            "link_id": link_id,
            "pass_rate": pass_rate
        }
        link_data['pass_rate'] = round(link_data['pass_rate'] * 100, 3)  # Convert ratio to %
        link_list.append(link_data)
    link_list.sort(key=lambda i: i['link_id'])
    return render_template('grid.html', curr_page='Status Grid', nav_list=nav_list, title=title, link_list=link_list)


@app.route('/<int:link_id>')
def link_page(link_id: int):
    """
    This page allows a user to see the details for an individual link
    It looks up the link in the database based on the id, passed as
    the last element of the URL path rather than as a URL parameter.
    It then looks that link up in the database and provides all of its
    information

    :param link_id: The ID of the link being accessed
    """
    title = f"Link {link_id} Details"
    link = dbconnection.fetch_link(link_id)

    left_image_list = []
    right_image_list = []
    past_failure_list = []

    """ Gather recent images and group by camera """

    for image in link['image_list']:
        image["passed"] = bool(image["passed"])
        img_data = {
            "date": image["time"].strftime('%Y-%m-%d'),
            "file": os.path.basename(image["filepath"]),
            "loop": image["loop_count"],
            "passed": image["passed"],
            "result": "Pass" if image['passed'] else "Failed",
            "time": image["time"].strftime('%H:%M:%S'),
            "timestamp": image["time"]  # Leave time stamp intact for sorting
        }
        if image["left_camera"]:
            left_image_list.append(img_data)
        else:
            right_image_list.append(img_data)

    """ Gather past failures """

    for image in link['past_failures']:
        image["passed"] = bool(image["passed"])
        image["left_camera"] = bool(image["left_camera"])
        img_data = {
            "camera": "Left" if image["left_camera"] else "Right",
            "date": image["time"].strftime('%Y-%m-%d'),
            "file": os.path.basename(image["filepath"]),
            "loop": image["loop_count"],
            "passed": image["passed"],
            "result": "Pass" if image['passed'] else "Failed",
            "time": image["time"].strftime('%H:%M:%S'),
            "timestamp": image["time"]  # Leave time stamp intact for sorting
        }
        past_failure_list.append(img_data)

    """ Compile link overview """

    # Check if the most recent images on either the left or right were a failure
    last_result = True
    if len(left_image_list) > 0:
        last_result = left_image_list[0]['passed']
    if len(right_image_list) > 0:
        last_result = last_result and right_image_list[0]['passed']  # Combine the left result with the right result
    link_data = {
        "id": link_id,
        "last_checked": link['image_list'][0]["time"].strftime('%H:%M - %m/%d/%Y'),
        "last_result": "PASS" if last_result else "FAIL",
    }

    return render_template('link.html',
                           curr_page=None,
                           nav_list=nav_list,
                           title=title,
                           link=link_data,
                           left_image_list=left_image_list,
                           right_image_list=right_image_list,
                           past_failure_list=past_failure_list)


@app.route('/configure', methods=['GET', 'POST'])
def configure():
    """
    The page for viewing and changing configuration values
    """

    """ Handle POST request """
    if request.method == "POST":
        config_file = package_to_config(request.form['_package'])  # Load the module's config values
        config = Config(config_file, autosave=False)
        for (key, value) in request.form.items():  # Update key values
            # Cast each value to the type it originally was
            if key in config and type(config[key]) is int:
                config.set_value(key, int(value))
            else:
                config.set_value(key, value)
        config.save()  # Save new config values
        if request.form["_package"] == "webserver":  # Reload webserver's config if altered
            CONFIG.reload()
        return redirect('/configure')

    """ Get filewatcher config file """
    with open(package_to_config("filewatcher")) as config_file:
        filewatcher_json = json.load(config_file)
        filewatcher = json_to_list(filewatcher_json)
    """ Get webserver config file """
    with open(f"{MODULE_DIR}/{CONFIG_FILE}") as config_file:
        webserver_json = json.load(config_file)
        webserver = json_to_list(webserver_json)

    return render_template('configure.html',
                           curr_page='Configure',
                           nav_list=nav_list,
                           filewatcher=filewatcher,
                           webserver=webserver,
                           title='Configure')


@app.route('/spec')
def documentation():
    # Provides a PDF of the ChainWatch documentation
    return app.send_static_file(CONFIG['SPEC_FILENAME'])


# ----------------------- Hidden pages

@app.route('/api', methods=['GET'])
def api():
    action = request.args.get('action')
    param = request.args.get('param')
    if action is None:
        return error_code("No 'action' provided")
    if action == 'updateQR':
        create_qr()
    elif action == 'resetDB':
        if param:
            try:
                param = int(param)
            except ValueError:
                error_code(f"'{param}' is not a valid integer")
            dbconnection.clear_img_database(param)
        else:
            print("CLEAR DB!!!!")
            # dbconnection.clear_img_database()
    else:
        return error_code(f"The action '{action}' is not supported")
    return jsonify({
        "status": "ok",
        "code": 200
    })


@app.route('/imgs/<path:filename>')
def imgs(filename):
    # The endpoint for accessing the link images
    return send_from_directory(CONFIG['MEDIA_FOLDER'], filename)


@app.route('/qr')
def qr():
    """
    Serves the pre-generated QR code that links to the homepage
    """
    return app.send_static_file('qr_code.jpg')


# =============================================================================================
# ===================================    LAUNCH SERVER    =====================================
# =============================================================================================


def start(port: int = None):
    global HOSTNAME, PORT
    load_config()
    PORT = CONFIG['PORT'] if port is None else port
    create_qr()
    app.run(host=HOSTNAME, port=PORT)


if __name__ == "__main__":
    """
    On script execution, start server
    """
    start()

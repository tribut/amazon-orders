#!/usr/bin/env python3
import argparse
import logging.config
from getpass import getpass
import os

from selenium import webdriver
from selenium.webdriver.firefox import firefox_binary


LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
DEFAULT_LOGLEVEL = logging.WARNING
logging.basicConfig(level=DEFAULT_LOGLEVEL, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


_AMAZON_DE_LOGIN_URL = r"https://www.amazon.de/ap/signin?_encoding=UTF8&openid.assoc_handle=deflex&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.mode=checkid_setup&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0&openid.ns.pape=http%3A%2F%2Fspecs.openid.net%2Fextensions%2Fpape%2F1.0&openid.pape.max_auth_age=0&openid.return_to=https%3A%2F%2Fwww.amazon.de%2Fref%3Dnav_signin"


# selenium doesn't seem to work with Firefox 48.
# it works with FF 47
_FIREFOX_DIR = os.path.join(os.path.expanduser("~"), "firefox_47")
_FIREFOX_PATH = os.path.join(_FIREFOX_DIR, "firefox")
ff_binary = None
if os.path.exists(_FIREFOX_PATH) and os.path.isfile(_FIREFOX_PATH):
    ff_binary = firefox_binary.FirefoxBinary(firefox_path=_FIREFOX_PATH)

else:
    logger.error("Can't find Firefox 47! Please download it from {} and extract it to '{}'. Trying with your installed Firefox version...".format(
        "http://download.cdn.mozilla.net/pub/firefox/releases/47.0.1/",
        _FIREFOX_DIR))

try:
    driver = webdriver.Firefox(firefox_binary=ff_binary)
except RuntimeError as re:
    logger.critical(re)
    raise re


def login(email, password):
    logger.info("Logging in...")
    driver.get(_AMAZON_DE_LOGIN_URL)

    email_input = driver.find_element_by_id("ap_email")
    email_input.send_keys(email)

    password_input = driver.find_element_by_id("ap_password")
    password_input.send_keys(password)

    login_button = driver.find_element_by_id("signInSubmit")
    login_button.click()

    assert "Ein Problem ist aufgetreten" not in driver.page_source
    logger.info("Login successful.")


def download_orders(email, password):
    """Starts downloading the orders.

    Uses the given email and password to login,
    and exports the orders from this Amazon.de account.

    Arguments:
        email (string) -- The amazon.de account's email
        password (string) -- The amazon.de account's password
    """
    login(email, password)


if __name__ == '__main__':
    argparser = argparse.ArgumentParser(description="Export your orders from amazon.de.")
    argparser.add_argument("-v", "--verbose",
                               action="count",
                               help="Increase the loglevel. More vs = more output.")
    args = argparser.parse_args()

    # see https://docs.python.org/2/library/logging.html#logging-levels
    log_level = DEFAULT_LOGLEVEL - args.verbose * 10 if args.verbose else DEFAULT_LOGLEVEL
    logging.basicConfig(level=log_level, format=LOG_FORMAT)

    print("Please enter your amazon.de login data...")
    email = input("email: ")
    password = getpass("password: ")
    orders = download_orders(email, password)

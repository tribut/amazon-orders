#!/usr/bin/env python3
import argparse
import logging.config
from getpass import getpass
import os
import json

import requests
from bs4 import BeautifulSoup


LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
DEFAULT_LOGLEVEL = logging.WARNING
logger = logging.getLogger(__name__)


_AMAZON_DE_LOGIN_FORM_ACTION = r"https://www.amazon.de/ap/signin"
_AMAZON_DE_ORDER_HISTORY = r"https://www.amazon.de/gp/css/order-history"


_INCLUDE_FREE = False


session = requests.Session()
session.headers = {
    "User-Agent": "Mozilla/5.0"
}


def hidden_form_fields(form_descriptor, soup, by_attribute="name"):
    form = [f for f in soup.find_all("form") if f.has_attr(by_attribute) and f[by_attribute] == form_descriptor][0]

    if not form:
        logger.critical("Form with {}: '{}' not found!".format(by_attribute, form_descriptor))
        return None

    data = {}
    hidden_form_fields = [f for f in form.find_all("input") if f["type"] == "hidden"]
    for hidden_field in hidden_form_fields:
        name = hidden_field["name"]
        value = hidden_field["value"]

        data[name] = value

    return data


def login(email, password):
    main_html = session.get(r"https://www.amazon.de").content
    main_soup = BeautifulSoup(main_html, "html.parser")

    login_page_url = main_soup.select("div#nav-flyout-ya-signin a")[0]["href"]
    logger.info("Logging in...")

    login_data = {
        "email": email,
        "password": password,
    }

    html = session.get(login_page_url).content
    soup = BeautifulSoup(html, "html.parser")

    login_data = hidden_form_fields("signIn", soup)
    session.post(_AMAZON_DE_LOGIN_FORM_ACTION, data=login_data)

    h = str(session.get(r"https://amazon.de").content)
    assert "Ein Problem ist aufgetreten" not in h and "Hallo! Anmelden" not in h
    logger.info("Login successful.")


def extract_orders_from_current_page():
    """Extracts the orders from the page the selenium WebDriver is currently on.

    Loops through the elements found on the current order page and collects their data:
    - order number
    - the date the order was created on
    - the total amount
    - the link to amazon's details page

    Returns:
        [dict] -- a list containing the found orders
    """
    orders = []

    order_elements = driver.find_elements_by_class_name("order")
    for order_element in order_elements:
        order_number = None
        order_date = None
        order_total = None
        order_details_link = None

        # the whole top part of an order, with its date, sum, and order number
        order_info = order_element.find_element_by_css_selector(".order-info")

        order_info_left = order_info.find_element_by_class_name("a-col-left")
        order_info_right = order_info.find_element_by_class_name("a-col-right")

        # the left part's parts
        info_cols = order_info_left.find_elements_by_class_name("a-column")
        for col in info_cols:
            try:
                description = col.find_element_by_class_name("a-size-mini").text
                value = col.find_element_by_class_name("a-size-base").text
            except NoSuchElementException:
                pass  # occurs for digital orders for the "recipient column"

            if description.lower() == "summe":
                order_total = float(value.replace("EUR ", "").replace(",", "."))

            elif description.lower() == "bestellung aufgegeben":
                order_date = value


        order_number = order_info_right.find_element_by_css_selector(".a-size-mini").text
        order_details_link = order_info_right.find_element_by_css_selector(".a-size-base a.a-link-normal").get_attribute("href")

        order = {
            "order_number": order_number,
            "order_date": order_date,
            "order_total": order_total,
            "order_details_link": order_details_link
        }
        logger.info("Found order: {}".format(order))

        try:
            if "Erstattet" in order_element.find_element_by_class_name("shipment").text:
                logger.warning("Order {} was returned and refunded. Ignoring.".format(order_number))
                continue
        except NoSuchElementException:
            pass  # digital orders

        if not _INCLUDE_FREE and order_total == 0.0:
            logger.warning("Order {} was free. Ignoring.".format(order_number))
            continue

        orders.append(order)

    return orders



def download_orders(email, password, include_free=False):
    """Starts downloading the orders.

    Uses the given email and password to login,
    and exports the orders from this Amazon.de account.

    Arguments:
        email (string) -- The amazon.de account's email
        password (string) -- The amazon.de account's password
    """
    global driver
    global _INCLUDE_FREE
    _INCLUDE_FREE = include_free

    try:
        driver = webdriver.Firefox(firefox_binary=ff_binary)
    except RuntimeError as re:
        logger.critical(re)
        raise re

    login(email, password)

    driver.get(_AMAZON_DE_ORDER_HISTORY)

    orders = []
    more_years = True
    year_ids = [element.get_attribute("id") for element in driver.find_elements_by_css_selector("[id^=orderFilterEntry-year-]")]
    for year_id in year_ids:
        logger.info("Extracting {}...".format(year_id))
        year_button = driver.find_element_by_id(year_id)
        year_button.click()

        more_pages = True
        while more_pages:
            orders.extend(extract_orders_from_current_page())

            try:
                next_page_button = driver.find_element_by_css_selector(".a-last a")
                next_page_button.click()
            except NoSuchElementException as nsee:
                more_pages = False

    driver.close()
    logger.info("Extracted {} orders.".format(len(orders)))
    return orders


def generate_json(orders, filepath=None):
    orders_json = json.dumps(orders, indent=4)

    if filepath is not None:
        logger.info("Saving exported orders to {}".format(filepath))
        with open(filepath, "w+") as f:
            f.write(orders_json)

    return orders_json


def generate_csv(orders, filepath=None):
    delimiter = "|"

    csv = []
    for order in orders:
        columns = [
            order["order_date"],
            str(order["order_total"]),
            order["order_number"],
            order["order_details_link"]
        ]
        line = delimiter.join(columns)
        csv.append(line)

    if filepath is not None:
        logger.info("Saving exported orders to {}".format(filepath))
        with open(filepath, "w+") as f:
            f.write("\n".join(csv))

    return csv


if __name__ == '__main__':
    argparser = argparse.ArgumentParser(description="Export your orders from amazon.de.")
    argparser.add_argument("-v", "--verbose",
                               action="count",
                               help="Increase the loglevel. More vs = more output.")
    argparser.add_argument("-j", "--json",
                           action="store",
                           metavar="FILE",
                           help="Save the orders as json to the specified file.")
    argparser.add_argument("-c", "--csv",
                           action="store",
                           metavar="FILE",
                           help="Save the orders as csv to the specified file.")
    argparser.add_argument("--include_free",
                           action="store_true",
                           help="Include free orders.")
    args = argparser.parse_args()

    # see https://docs.python.org/2/library/logging.html#logging-levels
    log_level = DEFAULT_LOGLEVEL - args.verbose * 10 if args.verbose else DEFAULT_LOGLEVEL
    logging.basicConfig(level=log_level, format=LOG_FORMAT)

    print("Please enter your amazon.de login data...")
    email = input("email: ")
    password = getpass("password: ")
    orders = download_orders(email, password, include_free=args.include_free)

    if args.json:
        generate_json(orders, args.json)

    if args.csv:
        generate_csv(orders, args.csv)

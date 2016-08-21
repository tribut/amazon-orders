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


_AMAZON_DE_LOGIN_FORM_ACTION = "https://www.amazon.de/ap/signin"
_AMAZON_DE_ORDER_HISTORY = "https://www.amazon.de/gp/your-account/order-history"


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
    main_html = session.get("https://www.amazon.de")

    logger.info("Logging in...")

    html = session.get(_AMAZON_DE_ORDER_HISTORY).content  # redirects to the signin page
    soup = BeautifulSoup(html, "html.parser")

    login_data = hidden_form_fields("signIn", soup)
    login_data["email"] = email
    login_data["password"] = password

    for k, v in login_data.items():
        logger.debug("Login data: {} = {}".format(k, v))

    r = session.post(_AMAZON_DE_LOGIN_FORM_ACTION, data=login_data)
    h = r.content
    s = BeautifulSoup(h, "html.parser")

    alerts = [a.string.strip() for a in s.select(".a-alert-container li") if a.string is not None]
    for alert in alerts:
        logger.error("from Amazon: {}".format(alert))

    assert not alerts and "Ein Problem ist aufgetreten" not in s.string
    logger.info("Login successful.")


def extract_orders_from_page(soup):
    """Extracts the orders from the page the selenium WebDriver is currently on.

    Loops through the elements found on the current order page and collects their data:
    - order number
    - the date the order was created on
    - the total amount
    - the link to amazon's details page

    Arguments:
        soup (BeautifulSoup) -- The BeautifulSoup instance for the website's html.

    Returns:
        [dict] -- a list containing the found orders
    """
    orders = []

    order_elements = soup.select(".order")
    for order_element in order_elements:
        order_number = None
        order_date = None
        order_total = None
        order_details_link = None

        # the whole top part of an order, with its date, sum, and order number
        order_info = [order_element.select(".order-info")][0]

        order_info_left = [order_info.select(".a-col-left")][0]
        order_info_right = [order_info.select(".a-col-right")][0]

        # the left part's parts
        info_cols = order_info_left.select(".a-column")
        for col in info_cols:
            try:
                description = [col.select(".a-size-mini")][0].string
                value = [col.select(".a-size-base")][0].string
            except IndexError:
                pass  # occurs for digital orders for the "recipient column"

            if description.lower() == "summe":
                order_total = float(value.replace("EUR ", "").replace(",", "."))

            elif description.lower() == "bestellung aufgegeben":
                order_date = value


        order_number = [order_info_right.select(".a-size-mini")][0].string
        order_details_link = [
            order_info_right.select(".a-size-base a.a-link-normal").get_attribute("href")
        ][0]

        order = {
            "order_number": order_number,
            "order_date": order_date,
            "order_total": order_total,
            "order_details_link": order_details_link
        }
        logger.info("Found order: {}".format(order))

        try:
            if "Erstattet" in [order_element.select(".shipment")][0].string:
                logger.warning("Order {} was returned and refunded. Ignoring.".format(order_number))
                continue
        except IndexError:
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
    global _INCLUDE_FREE
    _INCLUDE_FREE = include_free

    try:
        login(email, password)
    except AssertionError:
        logger.critical("Login failed!")
        return None

    orders_main_html = session.get(_AMAZON_DE_ORDER_HISTORY).content
    orders_main_soup = BeautifulSoup(orders_main_html, "html.parser")

    year_selection_form_data = hidden_form_fields("timePeriodForm", orders_main_soup, by_attribute="id")
    years = [o["value"] for o in orders_main_soup.select("select#orderFilter option") if "year" in o["value"]]

    orders = []
    for year in years:
        logger.info("Extracting {}...".format(year))

        year_selection_form_data["orderFilter"] = year
        orders_page_html = session.get(_AMAZON_DE_ORDER_HISTORY, data=year_selection_form_data)
        orders_page_soup = BeautifulSoup(orders_page_html, "html.parser")

        ignore_classes = ["a-disabled", "a-selected", "a-last"]
        pagination_urls = [li for li in orders_page_html.select("ul.a-pagination li") if li["class"] not in ignore_classes]

        orders.extend(extract_orders_from_page(orders_page_soup))
        for pagination_url in pagination_urls:
            html = session.get(pagination_url)
            soup = BeautifulSoup(html, "html.parser")

            orders.extend(extract_orders_from_page(soup))

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

    # see https://docs.python.org/3/library/logging.html#logging-levels
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

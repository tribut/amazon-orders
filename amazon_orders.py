#!/usr/bin/env python3
import argparse
import logging.config
from getpass import getpass
import os
import json

import dryscrape


LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
DEFAULT_LOGLEVEL = logging.INFO
logger = logging.getLogger(__name__)

_AMAZON_DE_ORDER_HISTORY = "https://www.amazon.de/gp/your-account/order-history"

_INCLUDE_FREE = False

session = dryscrape.Session()
session.headers = {
    "User-Agent": "Mozilla/5.0"
}


def login(email, password, otp):
    logger.info("Logging in...")

    session.visit(_AMAZON_DE_ORDER_HISTORY)  # redirects to the signin page
    html = session.body()

    email_field = session.at_css("#ap_email")
    password_field = session.at_css("#ap_password")

    email_field.set(email)
    password_field.set(password)

    session.at_css("#signInSubmit").click()  # email_field.form().submit() redirects to login with captcha. :(

    alerts = session.css(".a-alert-container li")
    for alert in alerts:
        logger.error("from Amazon: {}".format(alert.text()))

    assert not alerts and "Ein Problem ist aufgetreten" not in session.body()

    otp_field = session.at_css("#auth-mfa-otpcode")
    if otp_field is not None:
        logger.info("Two-factor authentication detected, sending OTP...")
        otp_field.set(otp)
        session.at_css("#auth-signin-button").click()

    alerts = session.css(".a-alert-container li")
    for alert in alerts:
        logger.error("from Amazon: {}".format(alert.text()))

    assert not alerts and "Ein Problem ist aufgetreten" not in session.body()

    logger.info("Login successful.")


def extract_orders_from_page():
    """Extracts the orders from the page the dryscrape driver is currently on.

    Loops through the elements found on the current order page and collects their data:
    - order number
    - the date the order was created on
    - the total amount
    - the link to amazon's details page

    Returns:
        list -- a list containing orders found on the current page
    """
    orders = []

    order_elements = session.css(".order")
    for order_element in order_elements:
        order_number = None
        order_date = None
        order_total = None
        order_details_link = None

        # the whole top part of an order, with its date, sum, and order number
        order_info = order_element.at_css(".order-info")

        order_info_left = order_info.at_css(".a-col-left")
        order_info_right = order_info.at_css(".a-col-right")

        # the left part's parts
        info_cols = order_info_left.css(".a-column")
        for col in info_cols:
            try:
                description = col.at_css(".a-size-mini").text()
                value = col.at_css(".a-size-base").text()
            except AttributeError:
                pass  # occurs for digital orders for the "recipient column"

            if description.lower() == "summe":
                order_total = float(value.replace("EUR ", "").replace(",", "."))

            elif description.lower() == "bestellung aufgegeben":
                order_date = value


        order_number = order_info_right.at_css(".a-size-mini").text()
        order_details_link = order_info_right.at_css(".a-size-base a.a-link-normal").get_attr("href")

        order = {
            "order_number": order_number,
            "order_date": order_date,
            "order_total": order_total,
            "order_details_link": order_details_link
        }
        logger.debug("Found order: {}".format(order))

        try:
            if "Erstattet" in order_element.at_css(".shipment").text():
                logger.warning("Order {} was returned and refunded. Ignoring.".format(order_number))
                continue
        except AttributeError:
            pass  # digital orders

        if not _INCLUDE_FREE and order_total == 0.0:
            logger.warning("Order {} was free. Ignoring.".format(order_number))
            continue

        orders.append(order)

    return orders



def download_orders(email, password, otp, include_free=False):
    """Starts downloading the orders.

    Uses the given email and password to login,
    and exports the orders from this Amazon.de account.

    Arguments:
        email (string) -- The amazon.de account's email
        password (string) -- The amazon.de account's password

    Keyword Arguments:
        include_free {bool} -- Flag whether or not include free orders like free kindle books or apps (default: {False})

    Returns:
        list -- List of orders found for the account or None, when the login fails
    """
    global _INCLUDE_FREE
    _INCLUDE_FREE = include_free

    try:
        login(email, password, otp)
    except AssertionError:
        logger.critical("Login failed!")
        return None

    session.visit(_AMAZON_DE_ORDER_HISTORY)

    years = [o.get_attr("value") for o in session.css("#orderFilter option") if "year" in o.get_attr("value")]

    orders = []
    for year in years:
        logger.info("Extracting {}...".format(year.replace("-", " ")))
        session.at_css("#orderFilter").set(year)
        session.at_css("#timePeriodForm").submit()

        orders_page_html = session.body()

        pagination_urls = [li.at_css("a").get_attr("href") for li in session.css("ul.a-pagination li") if li.get_attr("class") == "a-normal"]

        orders.extend(extract_orders_from_page())
        for pagination_url in pagination_urls:
            session.visit("https://www.amazon.de{}".format(pagination_url))

            orders.extend(extract_orders_from_page())

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
    otp = getpass("two-factor code (if applicable): ")
    orders = download_orders(email, password, otp, include_free=args.include_free)

    if args.json:
        generate_json(orders, args.json)

    if args.csv:
        generate_csv(orders, args.csv)

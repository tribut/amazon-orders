amazon-orders
=============
Export your orders from amazon.de

Based on the idea of [CyberLine/amazon-parser](https://github.com/CyberLine/amazon-parser),
this allows you to export your orders from amazon.de.

This is only tested on amazon.de, since amazon.com offers an [integrated CSV export](https://www.amazon.com/gp/b2b/reports) of your orders, amazon.de does not.


## Install
1. Create a pyvenv: `pyvenv venv`
1. Install the requirements: `venv/bin/pip install -r requirements.txt`
1. Download Firefox 47 (see below)


## Firefox Version
This uses [selenium](http://selenium-python.readthedocs.io/) and requires Firefox 47,
since it doesn't seem to work anymore with Firefox 48.

Download Firefox 47 from http://download.cdn.mozilla.net/pub/firefox/releases/47.0.1/ and extract it to a directory called "firefox_47" your home directory.  
`~/firefox_47/firefox` is used as the firefox binary as a workaround for this.

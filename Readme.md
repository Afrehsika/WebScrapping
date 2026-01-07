Skincare Product Web Scraping Project

Source Website: https://qudobeauty.com

Task: Part 1 (Day 1) – Scrape & Structure Skincare Product Data

📌 Project Overview

This project focuses on scraping and structuring skincare product data from Qudo Beauty, an e-commerce platform. The objective was to collect 20–30 skincare products and organize the data into a clean, structured dataset suitable for analysis, reporting, or further product development.

The scraper is designed to handle real-world inconsistencies in e-commerce pages by applying multiple fallback strategies for missing or variably structured data.

🎯 Objectives

Access and scrape product data from https://qudobeauty.com

Extract relevant skincare product attributes

Structure the data into a machine-readable format

Deliver a reusable scraping script and structured dataset

🛠 Tools & Technologies

Python 3

Requests – HTTP requests

BeautifulSoup (bs4) – HTML parsing

Pandas – data structuring and export

lxml – HTML parser

Regex (re) – pattern-based extraction

Time – request throttling

📊 Data Fields Collected

Each product record contains the following fields:

Field	Description
product_name	Name of the skincare product
brand	Brand name
category	Product category/type
ingredients	Ingredients list or description
size_packaging	Product size or packaging
product_image_url	URL of the product image
product_page_url	URL of the product page
🧠 Scraping Logic
1. Product Link Collection

Starts from the shop page (/shop)

Iterates through pagination

Collects unique product URLs

Stops automatically when no new products are found

Enforces safety limits to avoid infinite loops

2. Product Detail Extraction

For each product page:

Product Name: extracted using page headers and metadata fallbacks

Product Image: retrieved from gallery elements or Open Graph metadata

Category: extracted from WooCommerce categories or breadcrumb navigation

Ingredients: sourced from attributes tables, ingredient headings, description tabs, or regex matching

Brand: extracted from attributes, metadata, JSON-LD structured data, or inferred from categories

Size/Packaging: extracted from attributes or detected using regex (e.g., ml, g, oz)

3. Request Handling

Custom browser headers used

Request delays added to reduce server load

Exceptions handled gracefully to prevent script crashes

⚠️ Challenges & Solutions
Inconsistent Page Structure

Some products did not list ingredients, brand, or size in consistent locations.

Solution:
Implemented multiple fallback extraction strategies for each field.

Missing Brand Information

Several product pages lacked explicit brand tags.

Solution:
Brand was inferred using metadata, structured data (JSON-LD), and category labels as a fallback.

Pagination Variability

Pagination behavior varied across pages.

Solution:
Applied page limits and “no new links” detection logic.

🔍 Assumptions

Only products listed under the shop section were considered.

Ingredient descriptions within product descriptions were accepted as valid ingredients.

Brand inference was used only when explicit brand data was unavailable.

Priority was given to data completeness over perfect uniformity.
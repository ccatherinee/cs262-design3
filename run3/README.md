## Database Setup

CREATE TABLE Users (username VARCHAR(255) NOT NULL, password VARCHAR(255) NOT NULL, logged_in bool, PRIMARY KEY (username));

CREATE TABLE Messages (uuid int UNSIGNED NOT NULL, sentto VARCHAR(255), sentfrom VARCHAR(255), msg VARCHAR(255), timestamp TIMESTAMP, PRIMARY KEY (uuid));

## Engineering Notebook
https://docs.google.com/document/d/1n2iYZjubdItlVJJVLjnoLfShxECxl13D0iDaaWkX7rg/edit
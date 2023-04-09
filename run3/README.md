## Database Setup

Install MySQL, giving the root user a strong password. Create a user with username DB_user and password DB_password (constants in constant.py). Give it all of the MySQL permissions. 

Create three separate databases named server_1, server_2, and server_3. In each of the three databases, run the following two commands to create two tables:

CREATE TABLE Users (username VARCHAR(255) NOT NULL, password VARCHAR(255) NOT NULL, logged_in bool, PRIMARY KEY (username));
CREATE TABLE Messages (uuid int UNSIGNED NOT NULL, sentto VARCHAR(255), sentfrom VARCHAR(255), msg VARCHAR(255), timestamp TIMESTAMP, PRIMARY KEY (uuid));

## How to Run
python server.py [server number - either 1, 2, or 3] [is_primary - either true or false] to start up each server

python client.py to start up a client

## Engineering Notebook
https://docs.google.com/document/d/1n2iYZjubdItlVJJVLjnoLfShxECxl13D0iDaaWkX7rg/edit
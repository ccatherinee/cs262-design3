## Codebase / Database Setup

Clone this GitHub repository. Install Python (latest version) and MySQL, giving the root user a strong password. Create a user with username DB_user and password DB_password (corresponding to the constants in constant.py, which should be updated). Give that user all of the MySQL permissions. 

Create three separate databases using MySQL named server_1, server_2, and server_3. In each of the three databases, run the following two commands to create two separate tables, one storing all users of the chat application, and the other storing all messages sent:

CREATE TABLE Users (username VARCHAR(255) NOT NULL, password VARCHAR(255) NOT NULL, logged_in bool, PRIMARY KEY (username));
CREATE TABLE Messages (uuid int UNSIGNED NOT NULL, sentto VARCHAR(255), sentfrom VARCHAR(255), msg VARCHAR(255), timestamp TIMESTAMP, PRIMARY KEY (uuid));

More technical details about the database can be found in the engineering notebook.

Finally, set the 3 tuples of HOST/PORT constants in constants.py to the appropriate hosts/ports where you would like to run server 1, 2, and 3 respectively. Be sure to not use "" or "localhost," for example, but to use the explicit IP address of your computer/server.

## How to Run
To run the servers, run python server.py 1 true, python server.py 2 false, and then python server.py 3 false. This designates server 1 as the primary server. In general, the syntax is as follows:
python server.py [server number - either 1, 2, or 3] [is_primary - either true or false]

To run a clients, after having run the servers, simply run python client.py

Importantly: users should always logout before killing/control-C-ing the client!

## How to Use the Chat Application
There are 6 available application-related commands for the client to use: register, login, logout, delete, send, and find. 
* register [username] [password] allows users to create an account. register must be run from a non-logged in client. Note that register does not automatically login after the account is successfully registered. To login, users must separately submit a login command. 
    * Register will have a confirmation message if it was successfully completed, and it will have an error message if not (e.g., for incorrect command syntax, usernames and/or passwords too long or usernames having certain special characters, username already existing, or for current client already being logged in).
* login [username] [password] allows users to login once they have an account. login must be run from a non-logged in client.
    * Login will have a confirmation message if it was successfully completed, and it will have an error message if not (e.g., for incorrect command syntax, usernames and/or passwords too long, usernames having certain special characters, incorrect username or password, desired account already logged in elsewhere, or for current client already being logged in).  
* logout ignores any arguments given, and allows the currently logged-in user to logout, without killing the client. logout must be run from a logged-in client.
    * Logout will have a confirmation message if it was successfully completed, and it will have an error message if not (e.g., for user not being logged in currently).
* delete ignores any arguments given, and allows the currently logged-in user to delete that account. delete must be run from a logged-in client.
    * Delete will have a confirmation message if it was successfully completed, and it will have an error message if not (e.g., for user not being logged in currently).
* send [username] [message] allows users to send a message to a specified user. send must be run from a logged-in client.
    * Send will have no confirmation message if it was successfully completed, and it will have an error message if not (e.g., incorrect syntax, message or username too long, current client not being logged in, or recipient username not existing as an account).
* find [regex] allows users to find users on the chatbot by a regex expression.
    * Find will return the result of the user search if it was successfully completed, and it will have an error message otherwise (e.g., incorrect syntax or regex expression too long).
    * For specific details on how Python regex works, please see [this documentation](https://www.w3schools.com/python/python_regex.asp). The most important thing to note is that "." is a wildcard character. Note also that our regex matches a username if the beginning of the username matches the regex expression (e.g., "." will thus match any username). 

Therefore, a typical workflow in the chat application might look like: "register User1 Password1", "login User1 Password1", some "send" or "find" commands, and finally a "logout" or "delete." There is a limit on username/password/message size, but it is very large and probably will not be encountered in everyday use. 

Note that to close the server, you can press Control-C, which you can likewise do with the clients, as long as you logout or delete beforehand, if you are logged in. Finally, you can also type "help" or "?" into the client command line to receive further help or clarification on any of the above commands. Note also that the command-line input will give an error message stating a command is of unknown syntax if it does not belong to one of the above forms (matching lowercase and all).

## Engineering Notebook
Any and all technical/design details can be found in the engineering notebook: https://docs.google.com/document/d/1n2iYZjubdItlVJJVLjnoLfShxECxl13D0iDaaWkX7rg/edit.

## Terminology
The code refers to servers and replicas, which refer to the same thing. PR refers to the primary replica (the replica that clients talk to), while SR refers to any secondary replica (which only communicate with the primary replica).

## Testing
Note: for the database tests in tests.py to work, create a separate database called "cs262_testing" with the same users and messages tables in it. All comprehensive unit tests (testing individual function functionality) are located in tests.py.
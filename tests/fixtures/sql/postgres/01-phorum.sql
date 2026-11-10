-- Phorum 3 on PostgreSQL (only the columns Papercut uses), then the repo's patch script
CREATE ROLE papercut LOGIN PASSWORD 'papercut';
CREATE DATABASE phorum ENCODING 'UTF8';
\connect phorum

CREATE TABLE forums (
  id integer NOT NULL PRIMARY KEY,
  name varchar(50) NOT NULL DEFAULT '',
  active smallint NOT NULL DEFAULT 1,
  description varchar(255) NOT NULL DEFAULT '',
  table_name varchar(50) NOT NULL DEFAULT '',
  email_list varchar(50) NOT NULL DEFAULT '',
  email_return varchar(50) NOT NULL DEFAULT ''
);
CREATE TABLE forum_1 (
  id integer NOT NULL PRIMARY KEY,
  datestamp timestamp NOT NULL,
  thread integer NOT NULL DEFAULT 0,
  parent integer NOT NULL DEFAULT 0,
  author varchar(50) NOT NULL DEFAULT '',
  subject varchar(255) NOT NULL DEFAULT '',
  email varchar(200) NOT NULL DEFAULT '',
  host varchar(50) NOT NULL DEFAULT '',
  email_reply char(1) NOT NULL DEFAULT 'N',
  approved char(1) NOT NULL DEFAULT 'N',
  msgid varchar(100) NOT NULL DEFAULT '',
  modifystamp integer NOT NULL DEFAULT 0,
  userid integer NOT NULL DEFAULT 0
);
CREATE TABLE forum_1_bodies (
  id integer NOT NULL PRIMARY KEY,
  body text NOT NULL,
  thread integer NOT NULL DEFAULT 0
);
CREATE TABLE forums_auth (
  id integer NOT NULL PRIMARY KEY,
  name varchar(50) NOT NULL DEFAULT '',
  username varchar(50) NOT NULL DEFAULT '',
  password varchar(50) NOT NULL DEFAULT '',
  email varchar(200) NOT NULL DEFAULT ''
);
CREATE TABLE forums_moderators (
  user_id integer NOT NULL,
  forum_id integer NOT NULL
);

\i /papercut-storage/phorum_pgsql_fix.sql

INSERT INTO forums (id, nntp_group_name, name, description, table_name, email_list, email_return)
  VALUES (1, 'phorum.test', 'Test forum', 'A Phorum test forum', 'forum_1', 'list@example.com', 'return@example.com');
INSERT INTO forum_1 (id, datestamp, thread, parent, author, subject, email, host, approved, modifystamp) VALUES
  (1, '2024-01-01 10:00:00', 1, 0, 'Alice', 'First post', 'alice@example.com', '10.0.0.1', 'Y', 1704103200),
  (2, '2024-01-02 10:00:00', 1, 1, 'Bob', 'Re: First post', 'bob@example.com', '10.0.0.2', 'Y', 1704189600),
  (3, '2024-01-03 10:00:00', 3, 0, 'Spammer', 'Not approved', 'spam@example.com', '10.0.0.3', 'N', 1704276000),
  (4, '2024-01-04 10:00:00', 4, 0, 'Carol', 'Olá mundo', '', '10.0.0.4', 'Y', 1704362400);
INSERT INTO forum_1_bodies (id, body, thread) VALUES
  (1, 'Hello world', 1), (2, E'A reply\n.leading dot', 1), (3, 'spam', 3), (4, 'Corpo com acentuação', 4);
INSERT INTO forums_auth (id, name, username, password, email) VALUES
  (1, 'Moderator', 'moderator', MD5('secret'), 'mod@example.com'),
  (2, 'Old User', 'olduser', 'sefjKaLm7zybE', 'old@example.com');
INSERT INTO forums_moderators (user_id, forum_id) VALUES (1, 1);

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO papercut;

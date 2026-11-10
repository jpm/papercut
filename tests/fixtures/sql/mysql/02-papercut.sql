SET NAMES utf8mb4;
USE papercut;
-- the 'mysql' storage backend and auth module: the schema shipped in the repo
SOURCE /papercut-storage/mysql_storage.sql;
INSERT INTO papercut_groups (name, active, description, table_name)
  VALUES ('papercut.test', 1, 'Test group', 'papercut_default_table');
INSERT INTO papercut_default_table (id, datestamp, thread, parent, author, subject, bytes, line_num, host, body) VALUES
  (1, '2024-01-01 10:00:00', 1, 0, 'Alice', 'First post', 11, 1, '10.0.0.1', 'Hello world'),
  (2, '2024-01-02 10:00:00', 1, 1, 'Bob', 'Re: First post', 14, 2, '10.0.0.2', 'Olá, mundo\n.dot'),
  (3, '2024-01-03 10:00:00', 3, 0, 'Carol', 'Another thread', 5, 1, '10.0.0.3', 'third');
INSERT INTO papercut_groups_auth (name, username, password) VALUES ('papercut.test', 'alice', 'secret');

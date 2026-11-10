-- one database per backend family, and an unprivileged user for Papercut
CREATE DATABASE papercut CHARACTER SET utf8mb4;
CREATE DATABASE phorum CHARACTER SET utf8mb4;
CREATE DATABASE phpbb CHARACTER SET utf8mb4;
CREATE DATABASE nuke CHARACTER SET utf8mb4;
CREATE DATABASE postnuke CHARACTER SET utf8mb4;
CREATE USER 'papercut'@'%' IDENTIFIED BY 'papercut';
GRANT SELECT, INSERT, UPDATE, DELETE ON papercut.* TO 'papercut'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON phorum.* TO 'papercut'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON phpbb.* TO 'papercut'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON nuke.* TO 'papercut'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON postnuke.* TO 'papercut'@'%';

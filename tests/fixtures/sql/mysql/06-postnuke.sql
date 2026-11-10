SET NAMES utf8mb4;
USE postnuke;
-- the postnuke_phpbb_mysql_users auth module only reads nuke_users
CREATE TABLE nuke_users (
  pn_uid int NOT NULL PRIMARY KEY,
  pn_uname varchar(25) NOT NULL DEFAULT '',
  pn_pass varchar(40) NOT NULL DEFAULT ''
);
INSERT INTO nuke_users (pn_uid, pn_uname, pn_pass) VALUES (2, 'alice', MD5('secret'));

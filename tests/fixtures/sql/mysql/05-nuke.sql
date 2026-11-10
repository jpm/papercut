SET NAMES utf8mb4;
USE nuke;
-- PHP-Nuke: phpBB with the nuke_bb prefix, and users in nuke_users
CREATE TABLE nuke_bbforums (
  forum_id smallint unsigned NOT NULL PRIMARY KEY,
  forum_name varchar(150) NOT NULL DEFAULT '',
  forum_desc text NOT NULL,
  forum_posts int unsigned NOT NULL DEFAULT 0,
  forum_topics int unsigned NOT NULL DEFAULT 0,
  forum_last_post_id int unsigned NOT NULL DEFAULT 0,
  auth_view tinyint NOT NULL DEFAULT 0
);
CREATE TABLE nuke_bbtopics (
  topic_id int unsigned NOT NULL AUTO_INCREMENT PRIMARY KEY,
  forum_id smallint unsigned NOT NULL DEFAULT 0,
  topic_title char(60) NOT NULL DEFAULT '',
  topic_poster int NOT NULL DEFAULT 0,
  topic_time int NOT NULL DEFAULT 0,
  topic_replies int unsigned NOT NULL DEFAULT 0,
  topic_status tinyint NOT NULL DEFAULT 0,
  topic_vote tinyint NOT NULL DEFAULT 0,
  topic_type tinyint NOT NULL DEFAULT 0,
  topic_first_post_id int unsigned NOT NULL DEFAULT 0,
  topic_last_post_id int unsigned NOT NULL DEFAULT 0
);
CREATE TABLE nuke_bbposts (
  post_id int unsigned NOT NULL AUTO_INCREMENT PRIMARY KEY,
  topic_id int unsigned NOT NULL DEFAULT 0,
  forum_id smallint unsigned NOT NULL DEFAULT 0,
  poster_id int NOT NULL DEFAULT 0,
  post_time int NOT NULL DEFAULT 0,
  poster_ip char(8) NOT NULL DEFAULT '',
  post_username varchar(25) NOT NULL DEFAULT '',
  enable_bbcode tinyint NOT NULL DEFAULT 1,
  enable_html tinyint NOT NULL DEFAULT 0,
  enable_smilies tinyint NOT NULL DEFAULT 1,
  enable_sig tinyint NOT NULL DEFAULT 1
);
CREATE TABLE nuke_bbposts_text (
  post_id int unsigned NOT NULL PRIMARY KEY,
  bbcode_uid char(32) NOT NULL DEFAULT '',
  post_subject char(60) NOT NULL DEFAULT '',
  post_text text NOT NULL
);
CREATE TABLE nuke_users (
  user_id int NOT NULL PRIMARY KEY,
  username varchar(25) NOT NULL DEFAULT '',
  user_password varchar(32) NOT NULL DEFAULT '',
  user_email varchar(255) NOT NULL DEFAULT '',
  user_posts int unsigned NOT NULL DEFAULT 0
);
CREATE TABLE nuke_bbauth_access (
  group_id int NOT NULL DEFAULT 0,
  forum_id smallint unsigned NOT NULL DEFAULT 0,
  auth_view tinyint NOT NULL DEFAULT 0
);
CREATE TABLE nuke_bbuser_group (
  group_id int NOT NULL DEFAULT 0,
  user_id int NOT NULL DEFAULT 0
);
-- (no patch script ships for PHP-Nuke; this is phpbb_mysql_fix.sql for nuke_bbforums)
ALTER TABLE nuke_bbforums ADD nntp_group_name VARCHAR(30) AFTER forum_name;
ALTER TABLE nuke_bbforums ADD UNIQUE (nntp_group_name);

INSERT INTO nuke_bbforums (forum_id, forum_name, nntp_group_name, forum_desc, forum_posts, forum_topics, forum_last_post_id, auth_view)
  VALUES (1, 'Test forum', 'nuke.test', 'A PHP-Nuke test forum', 3, 2, 3, 0);
INSERT INTO nuke_users (user_id, username, user_password, user_email, user_posts) VALUES
  (-1, 'Anonymous', '', '', 0),
  (2, 'alice', MD5('secret'), 'alice@example.com', 2);
INSERT INTO nuke_bbtopics (topic_id, forum_id, topic_title, topic_poster, topic_time, topic_replies, topic_first_post_id, topic_last_post_id) VALUES
  (1, 1, 'First topic', 2, 1704103200, 1, 1, 2),
  (2, 1, 'Olá mundo', -1, 1704276000, 0, 3, 3);
INSERT INTO nuke_bbposts (post_id, topic_id, forum_id, poster_id, post_time, poster_ip, post_username) VALUES
  (1, 1, 1, 2, 1704103200, '0a000001', ''),
  (2, 1, 1, 2, 1704189600, '0a000001', ''),
  (3, 2, 1, -1, 1704276000, '0a000002', 'Guest');
INSERT INTO nuke_bbposts_text (post_id, bbcode_uid, post_subject, post_text) VALUES
  (1, 'abc', 'First topic', 'Hello from PHP-Nuke'),
  (2, 'abc', '', 'A reply\n.leading dot'),
  (3, 'abc', 'Olá mundo', 'Corpo com acentuação');

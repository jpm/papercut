DROP TABLE IF EXISTS papercut_groups;
CREATE TABLE papercut_groups (          
  id int(10) unsigned NOT NULL auto_increment,
  name varchar(50) NOT NULL default '',
  active smallint(6) NOT NULL default '0',
  description varchar(255) NOT NULL default '',
  table_name varchar(50) NOT NULL default '',  
  PRIMARY KEY  (id),
  KEY name (name),  
  KEY active (active)
) TYPE=MyISAM;

DROP TABLE IF EXISTS papercut_groups_auth;
CREATE TABLE papercut_groups_auth (
  id int(10) unsigned NOT NULL auto_increment,
  sess_id varchar(32) NOT NULL default '',
  name varchar(50) NOT NULL default '',   
  username varchar(50) NOT NULL default '',
  password varchar(50) NOT NULL default '',
  PRIMARY KEY  (id),
  KEY name (name),  
  KEY username (username)
) TYPE=MyISAM;

DROP TABLE IF EXISTS papercut_default_table;
CREATE TABLE papercut_default_table (
  id int(10) unsigned NOT NULL default '0',
  datestamp datetime NOT NULL default '0000-00-00 00:00:00',
  thread int(10) unsigned NOT NULL default '0',
  parent int(10) unsigned NOT NULL default '0',
  author varchar(255) NOT NULL default '',
  subject varchar(255) NOT NULL default '',
  message_id varchar(255) NOT NULL default '',
  bytes int(10) unsigned NOT NULL default '0',
  line_num int(10) unsigned NOT NULL default '0',
  host varchar(15) NOT NULL default '',
  body text NOT NULL,
  PRIMARY KEY  (id), 
  KEY author (author),
  KEY datestamp (datestamp),
  KEY subject (subject),
  KEY thread (thread),  
  KEY parent (parent)   
) TYPE=MyISAM;

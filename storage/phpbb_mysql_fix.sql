#
# Please change the values here as appropriate to your 
# setup (i.e. table name or size of the 'nntp_group_name' field)
#
# Warning: Do not change the field name to something else than 'nttp_group_name'!
#
ALTER TABLE phpbb_forums ADD nntp_group_name VARCHAR(30) AFTER forum_name;
ALTER TABLE phpbb_forums ADD UNIQUE (nntp_group_name);

#
# After dumping this file into MySQL you will need to manually update the contents
# of the 'nttp_group_name' field to associate a table name / forum with a newsgroup to
# be available on Papercut
#